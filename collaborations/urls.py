from django.urls import path

from . import views

app_name = "collaborations"

urlpatterns = [
    path("offers/", views.OfferListView.as_view(), name="offer_list"),
    path("offers/create/", views.OfferCreateView.as_view(), name="offer_create"),
    path("offers/<int:pk>/", views.OfferDetailView.as_view(), name="offer_detail"),
    path("offers/<int:pk>/respond/", views.OfferRespondView.as_view(), name="offer_respond"),
    path(
        "offers/responses/",
        views.OfferResponseListView.as_view(),
        name="offer_responses",
    ),
    path(
        "offers/responses/<int:pk>/",
        views.OfferResponseDetailView.as_view(),
        name="offer_response_detail",
    ),
    path(
        "offers/responses/<int:pk>/accept/",
        views.OfferResponseAcceptView.as_view(),
        name="offer_response_accept",
    ),
    path(
        "offers/responses/<int:pk>/decline/",
        views.OfferResponseDeclineView.as_view(),
        name="offer_response_decline",
    ),
    path("bloggers/", views.BloggerRequestListView.as_view(), name="blogger_request_list"),
    path("bloggers/create/", views.BloggerRequestCreateView.as_view(), name="blogger_request_create"),
    path("bloggers/<int:pk>/", views.BloggerRequestDetailView.as_view(), name="blogger_request_detail"),
    path("bloggers/<int:pk>/respond/", views.BloggerRequestRespondView.as_view(), name="blogger_request_respond"),
    path("collaborations/", views.CollaborationListView.as_view(), name="collaboration_list"),
    path(
        "collaborations/<int:pk>/reviews/",
        views.CollaborationReviewUpdateView.as_view(),
        name="collaboration_review",
    ),
    path(
        "collaborations/<int:pk>/confirm/",
        views.confirm_collaboration_completion,
        name="collaboration_confirm",
    ),
    path(
        "collaborations/<int:pk>/fail/",
        views.mark_collaboration_failed,
        name="collaboration_fail",
    ),
]