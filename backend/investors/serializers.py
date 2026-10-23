from rest_framework import serializers

from investors.models import InvestorProfile


class InvestorListSerializer(serializers.ModelSerializer):
    """A lightweight serializer for a list of investors."""

    class Meta:
        model = InvestorProfile
        fields = [
            'investor_id',
            'investor_name',
            'investor_type',
            'investment_min',
        ]


class InvestorPublicProfileSerializer(serializers.ModelSerializer):
    """Public data of a single investor. Private fields are not exposed."""

    contact = serializers.SerializerMethodField()

    def get_contact(self, obj):
        return {'phone': obj.investor_phone}

    class Meta:
        model = InvestorProfile
        fields = [
            'investor_id',
            'investor_name',
            'investor_type',
            'investor_description',
            'contact',
            'investment_min',
            'is_verified',
        ]
