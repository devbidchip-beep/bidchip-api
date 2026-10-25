"""
FedEx REST API carrier integration (OAuth 2.0).

Credentials read from settings: FEDEX_CLIENT_ID, FEDEX_CLIENT_SECRET.
Token is cached for 50 minutes (FedEx tokens expire after 60 minutes).
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

FEDEX_BASE_URL = "https://apis.fedex.com"
FEDEX_AUTH_URL = f"{FEDEX_BASE_URL}/oauth/token"
FEDEX_RATE_URL = f"{FEDEX_BASE_URL}/rate/v1/rates/quotes"
FEDEX_SHIP_URL = f"{FEDEX_BASE_URL}/ship/v1/shipments"
FEDEX_TRACK_URL = f"{FEDEX_BASE_URL}/track/v1/trackingnumbers"

# FedEx service types considered next-day
_NEXT_DAY_SERVICE_TYPES = {
    "PRIORITY_OVERNIGHT",
    "FIRST_OVERNIGHT",
    "STANDARD_OVERNIGHT",
    "FEDEX_FIRST_OVERNIGHT_FREIGHT",
    "INTERNATIONAL_PRIORITY",
}


def _cm_to_in(cm: float) -> float:
    return round(cm / 2.54, 2)


def _kg_to_lbs(kg: float) -> float:
    return round(kg * 2.20462, 2)


def get_access_token() -> str:
    """
    OAuth2 client_credentials flow.
    Caches token for 50 minutes (FedEx tokens expire after 60 min).
    Reads FEDEX_CLIENT_ID, FEDEX_CLIENT_SECRET from settings.
    """
    cached = cache.get("fedex_access_token")
    if cached:
        return cached

    resp = requests.post(
        FEDEX_AUTH_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": settings.FEDEX_CLIENT_ID,
            "client_secret": settings.FEDEX_CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    cache.set("fedex_access_token", token, timeout=50 * 60)
    return token


def get_rates(
    shipper_address: dict,
    recipient_address: dict,
    packages: list[dict],
) -> list[dict]:
    """
    Call FedEx Rate API v1.

    shipper_address / recipient_address:
        {name, address_line, city, state, postal_code, country_code}
    packages:
        [{length_cm, width_cm, height_cm, weight_kg}]

    Returns list of:
        {service_code, service_name, amount, currency, transit_days, is_next_day}
    Returns [] on any error (logs the error, never raises to caller).
    """
    try:
        token = get_access_token()
    except Exception:
        logger.exception("FedEx: failed to obtain access token")
        return []

    def _fmt_address(addr: dict) -> dict:
        return {
            "streetLines": [addr.get("address_line", "")],
            "city": addr.get("city", ""),
            "stateOrProvinceCode": addr.get("state", ""),
            "postalCode": addr.get("postal_code", ""),
            "countryCode": addr.get("country_code", "US"),
        }

    pkg_list = []
    for pkg in packages:
        pkg_list.append(
            {
                "weight": {
                    "units": "LB",
                    "value": _kg_to_lbs(float(pkg["weight_kg"])),
                },
                "dimensions": {
                    "length": int(_cm_to_in(float(pkg["length_cm"]))),
                    "width": int(_cm_to_in(float(pkg["width_cm"]))),
                    "height": int(_cm_to_in(float(pkg["height_cm"]))),
                    "units": "IN",
                },
            }
        )

    payload = {
        "accountNumber": {"value": getattr(settings, "FEDEX_ACCOUNT_NUMBER", "")},
        "requestedShipment": {
            "shipper": {"address": _fmt_address(shipper_address)},
            "recipient": {"address": _fmt_address(recipient_address)},
            "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
            "rateRequestType": ["LIST", "ACCOUNT"],
            "requestedPackageLineItems": pkg_list,
        },
    }

    try:
        resp = requests.post(
            FEDEX_RATE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-locale": "en_US",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("FedEx: rate request failed")
        return []

    results = []
    rate_reply_details = data.get("output", {}).get("rateReplyDetails", [])

    for detail in rate_reply_details:
        try:
            service_type = detail["serviceType"]
            service_name = detail.get("serviceName", service_type)
            rated_shipment_details = detail.get("ratedShipmentDetails", [])
            if not rated_shipment_details:
                continue
            # Prefer ACCOUNT rate, fall back to LIST
            chosen_detail = next(
                (d for d in rated_shipment_details if d.get("rateType") == "ACCOUNT"),
                rated_shipment_details[0],
            )
            total_net = chosen_detail["totalNetCharge"]
            amount = float(total_net)
            currency = chosen_detail.get("currency", "USD")
            transit_days = detail.get("commit", {}).get("transitDays")
            if transit_days is not None:
                try:
                    transit_days = int(transit_days)
                except (ValueError, TypeError):
                    transit_days = None

            results.append(
                {
                    "service_code": service_type,
                    "service_name": service_name,
                    "amount": amount,
                    "currency": currency,
                    "transit_days": transit_days,
                    "is_next_day": service_type in _NEXT_DAY_SERVICE_TYPES,
                }
            )
        except (KeyError, ValueError, TypeError, IndexError):
            logger.exception("FedEx: failed to parse rate detail entry")
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
    Call FedEx Ship API to create a shipment and generate a label.

    Returns {tracking_number, label_base64, label_format} or None on error.
    """
    try:
        token = get_access_token()
    except Exception:
        logger.exception("FedEx: failed to obtain access token for label creation")
        return None

    def _fmt_contact_address(addr: dict) -> dict:
        return {
            "contact": {"personName": addr.get("name", ""), "phoneNumber": ""},
            "address": {
                "streetLines": [addr.get("address_line", "")],
                "city": addr.get("city", ""),
                "stateOrProvinceCode": addr.get("state", ""),
                "postalCode": addr.get("postal_code", ""),
                "countryCode": addr.get("country_code", "US"),
            },
        }

    pkg_list = []
    for i, pkg in enumerate(packages):
        item = {
            "sequenceNumber": i + 1,
            "weight": {
                "units": "LB",
                "value": _kg_to_lbs(float(pkg["weight_kg"])),
            },
            "dimensions": {
                "length": int(_cm_to_in(float(pkg["length_cm"]))),
                "width": int(_cm_to_in(float(pkg["width_cm"]))),
                "height": int(_cm_to_in(float(pkg["height_cm"]))),
                "units": "IN",
            },
        }
        if reference:
            item["customerReferences"] = [
                {"customerReferenceType": "CUSTOMER_REFERENCE", "value": reference}
            ]
        pkg_list.append(item)

    payload = {
        "labelResponseOptions": "URL_ONLY",
        "requestedShipment": {
            "shipper": _fmt_contact_address(shipper),
            "recipients": [_fmt_contact_address(recipient)],
            "serviceType": service_code,
            "packagingType": "YOUR_PACKAGING",
            "pickupType": "DROPOFF_AT_FEDEX_LOCATION",
            "shippingChargesPayment": {
                "paymentType": "SENDER",
                "payor": {
                    "responsibleParty": {
                        "accountNumber": {
                            "value": getattr(settings, "FEDEX_ACCOUNT_NUMBER", "")
                        }
                    }
                },
            },
            "labelSpecification": {
                "imageType": "PDF",
                "labelStockType": "PAPER_85X11_TOP_HALF_LABEL",
            },
            "requestedPackageLineItems": pkg_list,
        },
        "accountNumber": {"value": getattr(settings, "FEDEX_ACCOUNT_NUMBER", "")},
    }

    try:
        resp = requests.post(
            FEDEX_SHIP_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-locale": "en_US",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("FedEx: label creation request failed")
        return None

    try:
        output = data["output"]
        transaction_shipments = output.get("transactionShipments", [])
        if not transaction_shipments:
            logger.error("FedEx: no transactionShipments in response")
            return None
        txn = transaction_shipments[0]
        tracking_number = txn["masterTrackingNumber"]
        piece_responses = txn.get("pieceResponses", [])
        if not piece_responses:
            logger.error("FedEx: no pieceResponses in response")
            return None
        label_url = piece_responses[0].get("packageDocuments", [{}])[0].get("url", "")
        return {
            "tracking_number": tracking_number,
            "label_base64": label_url,  # URL rather than base64 when URL_ONLY mode
            "label_format": "PDF",
        }
    except (KeyError, IndexError, TypeError):
        logger.exception("FedEx: failed to parse label creation response")
        return None


def get_tracking(tracking_number: str) -> dict | None:
    """
    Call FedEx Track API to get current shipment status.
    Returns {status, description, timestamp} or None on error.
    """
    try:
        token = get_access_token()
        payload = {
            "includeDetailedScans": True,
            "trackingInfo": [
                {"trackingNumberInfo": {"trackingNumber": tracking_number}}
            ],
        }
        resp = requests.post(
            FEDEX_TRACK_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-locale": "en_US",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        complete_track = (
            data.get("output", {})
            .get("completeTrackResults", [{}])[0]
            .get("trackResults", [{}])[0]
        )
        latest_status = complete_track.get("latestStatusDetail", {})
        date_time = complete_track.get("dateAndTimes", [{}])[0]
        return {
            "status": latest_status.get("code", ""),
            "description": latest_status.get("description", ""),
            "timestamp": date_time.get("dateTime", ""),
        }
    except Exception:
        logger.exception("FedEx: tracking request failed for %s", tracking_number)
        return None
