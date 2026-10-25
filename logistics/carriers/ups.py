"""
UPS REST API carrier integration (OAuth 2.0).

Credentials read from settings: UPS_CLIENT_ID, UPS_CLIENT_SECRET.
Token is cached for 3.5 hours (UPS tokens expire after 4 hours).
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

UPS_BASE_URL = "https://onlinetools.ups.com"
UPS_AUTH_URL = f"{UPS_BASE_URL}/security/v1/oauth/token"
UPS_RATE_URL = f"{UPS_BASE_URL}/api/rating/v2403/Rate"
UPS_SHIP_URL = f"{UPS_BASE_URL}/api/shipments/v2403/ship"
UPS_TRACK_URL = f"{UPS_BASE_URL}/api/track/v1/details"

# Approximate mapping of UPS service codes to human-readable names
_SERVICE_NAMES = {
    "01": "UPS Next Day Air",
    "02": "UPS 2nd Day Air",
    "03": "UPS Ground",
    "07": "UPS Worldwide Express",
    "08": "UPS Worldwide Expedited",
    "11": "UPS Standard",
    "12": "UPS 3 Day Select",
    "13": "UPS Next Day Air Saver",
    "14": "UPS Next Day Air Early",
    "54": "UPS Worldwide Express Plus",
    "59": "UPS 2nd Day Air AM",
    "65": "UPS Worldwide Saver",
}

# Service codes considered next-day
_NEXT_DAY_CODES = {"01", "13", "14", "54"}


def _cm_to_in(cm: float) -> float:
    return round(cm / 2.54, 2)


def _kg_to_lbs(kg: float) -> float:
    return round(kg * 2.20462, 2)


def get_access_token() -> str:
    """
    OAuth2 client_credentials flow.
    Caches token for 3.5 hours (expires in 4 h).
    Reads UPS_CLIENT_ID and UPS_CLIENT_SECRET from settings.
    """
    cached = cache.get("ups_access_token")
    if cached:
        return cached

    resp = requests.post(
        UPS_AUTH_URL,
        data={"grant_type": "client_credentials"},
        auth=(settings.UPS_CLIENT_ID, settings.UPS_CLIENT_SECRET),
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    cache.set("ups_access_token", token, timeout=int(3.5 * 3600))
    return token


def get_rates(
    shipper_address: dict,
    recipient_address: dict,
    packages: list[dict],
) -> list[dict]:
    """
    Call UPS Rating API.

    shipper_address / recipient_address:
        {name, address_line, city, state, postal_code, country_code}
    packages:
        [{length_cm, width_cm, height_cm, weight_kg}]

    Converts cm to inches and kg to lbs.
    Returns list of:
        {service_code, service_name, amount, currency, transit_days, is_next_day}
    Returns [] on any error (logs the error, never raises to caller).
    """
    try:
        token = get_access_token()
    except Exception:
        logger.exception("UPS: failed to obtain access token")
        return []

    def _fmt_address(addr: dict) -> dict:
        return {
            "Name": addr.get("name", ""),
            "Address": {
                "AddressLine": [addr.get("address_line", "")],
                "City": addr.get("city", ""),
                "StateProvinceCode": addr.get("state", ""),
                "PostalCode": addr.get("postal_code", ""),
                "CountryCode": addr.get("country_code", "US"),
            },
        }

    pkg_list = []
    for pkg in packages:
        pkg_list.append(
            {
                "PackagingType": {"Code": "02"},  # Customer Supplied Package
                "Dimensions": {
                    "UnitOfMeasurement": {"Code": "IN"},
                    "Length": str(_cm_to_in(float(pkg["length_cm"]))),
                    "Width": str(_cm_to_in(float(pkg["width_cm"]))),
                    "Height": str(_cm_to_in(float(pkg["height_cm"]))),
                },
                "PackageWeight": {
                    "UnitOfMeasurement": {"Code": "LBS"},
                    "Weight": str(_kg_to_lbs(float(pkg["weight_kg"]))),
                },
            }
        )

    payload = {
        "RateRequest": {
            "Request": {"RequestOption": "Shop"},  # Shop = all services
            "Shipment": {
                "Shipper": _fmt_address(shipper_address),
                "ShipTo": _fmt_address(recipient_address),
                "ShipFrom": _fmt_address(shipper_address),
                "Package": pkg_list,
            },
        }
    }

    try:
        resp = requests.post(
            UPS_RATE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("UPS: rate request failed")
        return []

    results = []
    rated_shipments = (
        data.get("RateResponse", {})
        .get("RatedShipment", [])
    )
    if isinstance(rated_shipments, dict):
        rated_shipments = [rated_shipments]

    for rs in rated_shipments:
        try:
            svc_code = rs["Service"]["Code"]
            amount = float(rs["TotalCharges"]["MonetaryValue"])
            currency = rs["TotalCharges"]["CurrencyCode"]
            transit_days = None
            gtd = rs.get("GuaranteedDelivery", {})
            if gtd.get("BusinessDaysInTransit"):
                transit_days = int(gtd["BusinessDaysInTransit"])
            results.append(
                {
                    "service_code": svc_code,
                    "service_name": _SERVICE_NAMES.get(svc_code, f"UPS {svc_code}"),
                    "amount": amount,
                    "currency": currency,
                    "transit_days": transit_days,
                    "is_next_day": svc_code in _NEXT_DAY_CODES,
                }
            )
        except (KeyError, ValueError, TypeError):
            logger.exception("UPS: failed to parse rated shipment entry")
            continue

    return results


def create_label(
    shipper: dict,
    recipient: dict,
    packages: list[dict],
    service_code: str,
    reference: str = "",
) -> dict | None:
    """
    Call UPS Shipping REST API to create a shipment and generate a label.

    Returns {tracking_number, label_base64, label_format} or None on error.
    """
    try:
        token = get_access_token()
    except Exception:
        logger.exception("UPS: failed to obtain access token for label creation")
        return None

    def _fmt_address(addr: dict) -> dict:
        return {
            "Name": addr.get("name", ""),
            "Address": {
                "AddressLine": [addr.get("address_line", "")],
                "City": addr.get("city", ""),
                "StateProvinceCode": addr.get("state", ""),
                "PostalCode": addr.get("postal_code", ""),
                "CountryCode": addr.get("country_code", "US"),
            },
        }

    pkg_list = []
    for pkg in packages:
        pkg_list.append(
            {
                "Packaging": {"Code": "02"},
                "Dimensions": {
                    "UnitOfMeasurement": {"Code": "IN"},
                    "Length": str(_cm_to_in(float(pkg["length_cm"]))),
                    "Width": str(_cm_to_in(float(pkg["width_cm"]))),
                    "Height": str(_cm_to_in(float(pkg["height_cm"]))),
                },
                "PackageWeight": {
                    "UnitOfMeasurement": {"Code": "LBS"},
                    "Weight": str(_kg_to_lbs(float(pkg["weight_kg"]))),
                },
                "ReferenceNumber": [{"Value": reference}] if reference else [],
            }
        )

    payload = {
        "ShipmentRequest": {
            "Request": {"RequestOption": "nonvalidate"},
            "Shipment": {
                "Shipper": {
                    **_fmt_address(shipper),
                    "ShipperNumber": getattr(settings, "UPS_ACCOUNT_NUMBER", ""),
                },
                "ShipTo": _fmt_address(recipient),
                "ShipFrom": _fmt_address(shipper),
                "Service": {"Code": service_code},
                "Package": pkg_list,
            },
            "LabelSpecification": {
                "LabelImageFormat": {"Code": "GIF"},
            },
        }
    }

    try:
        resp = requests.post(
            UPS_SHIP_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("UPS: label creation request failed")
        return None

    try:
        shipment_results = data["ShipmentResponse"]["ShipmentResults"]
        tracking_number = shipment_results["ShipmentIdentificationNumber"]
        pkg_results = shipment_results.get("PackageResults", {})
        if isinstance(pkg_results, list):
            pkg_results = pkg_results[0]
        label_image = pkg_results["ShippingLabel"]["GraphicImage"]
        label_format = pkg_results["ShippingLabel"]["ImageFormat"]["Code"]
        return {
            "tracking_number": tracking_number,
            "label_base64": label_image,
            "label_format": label_format,
        }
    except (KeyError, IndexError, TypeError):
        logger.exception("UPS: failed to parse label creation response")
        return None


def get_tracking(tracking_number: str) -> dict | None:
    """
    Call UPS Tracking API to get current shipment status.
    Returns {status, description, timestamp} or None on error.
    """
    try:
        token = get_access_token()
        resp = requests.get(
            f"{UPS_TRACK_URL}/{tracking_number}",
            headers={
                "Authorization": f"Bearer {token}",
                "transId": tracking_number,
                "transactionSrc": "BidChip",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        activities = (
            data.get("trackResponse", {})
            .get("shipment", [{}])[0]
            .get("package", [{}])[0]
            .get("activity", [])
        )
        if not activities:
            return None
        latest = activities[0]
        return {
            "status": latest.get("status", {}).get("type", ""),
            "description": latest.get("status", {}).get("description", ""),
            "timestamp": latest.get("date", "") + " " + latest.get("time", ""),
        }
    except Exception:
        logger.exception("UPS: tracking request failed for %s", tracking_number)
        return None
