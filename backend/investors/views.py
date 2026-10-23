from rest_framework import generics, permissions
from rest_framework.pagination import PageNumberPagination

from investors.models import InvestorProfile
from investors.serializers import (
    InvestorListSerializer,
    InvestorPublicProfileSerializer,
)


class InvestorPagination(PageNumberPagination):
    """Custom pagination class to match the API specification."""

    page_size = 8
    page_size_query_param = 'page_size'
    max_page_size = 100


class VerifiedInvestorQuerysetMixin:
    """Only verified investors are public."""

    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return InvestorProfile.objects.filter(is_verified=True).order_by('investor_id')


class InvestorProfileListView(VerifiedInvestorQuerysetMixin, generics.ListAPIView):
    """API view to list verified investors with pagination."""

    serializer_class = InvestorListSerializer
    pagination_class = InvestorPagination


class InvestorPublicProfileDetailView(
    VerifiedInvestorQuerysetMixin, generics.RetrieveAPIView
):
    """Returns the public data of a single verified investor."""

    serializer_class = InvestorPublicProfileSerializer
    lookup_field = 'investor_id'
    lookup_url_kwarg = 'id'
