from rest_framework import filters, generics, permissions
from rest_framework.exceptions import ValidationError
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
    """API view to list verified investors with search, type filter and pagination."""

    serializer_class = InvestorListSerializer
    pagination_class = InvestorPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['investor_name']

    def get_queryset(self):
        """Optionally restricts the returned investors by type."""
        queryset = super().get_queryset()
        investor_type = self.request.query_params.get('type')
        if investor_type is None:
            return queryset

        if investor_type not in InvestorProfile.InvestorType.values:
            allowed = ', '.join(InvestorProfile.InvestorType.values)
            raise ValidationError({'type': f'Unknown type. Allowed values: {allowed}.'})

        return queryset.filter(investor_type=investor_type)


class InvestorPublicProfileDetailView(
    VerifiedInvestorQuerysetMixin, generics.RetrieveAPIView
):
    """Returns the public data of a single verified investor."""

    serializer_class = InvestorPublicProfileSerializer
    lookup_field = 'investor_id'
    lookup_url_kwarg = 'id'
