from django.urls import path

from bidding.views import AwardLineView, BidListView, PlaceBidView, WithdrawBidView

urlpatterns = [
    path("bids/", BidListView.as_view()),
    path("bids/place/", PlaceBidView.as_view()),
    path("bids/<uuid:pk>/withdraw/", WithdrawBidView.as_view()),
    path("lines/<uuid:line_id>/award/", AwardLineView.as_view()),
]
