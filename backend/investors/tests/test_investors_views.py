from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from investors.models import InvestorProfile

User = get_user_model()

pytestmark = pytest.mark.api

LIST_FIELDS = {'investor_id', 'investor_name', 'investor_type', 'investment_min'}
DETAIL_FIELDS = {
    'investor_id',
    'investor_name',
    'investor_type',
    'investor_description',
    'contact',
    'investment_min',
    'is_verified',
}
PRIVATE_FIELDS = {'user', 'edrpou_or_ipn', 'email'}


def create_investor(index, **overrides):
    user = User.objects.create_user(
        email=f'investor{index}@test.com',
        first_name='Name',
        last_name='Surname',
        role='investor',
    )
    fields = {
        'user': user,
        'investor_name': f'Investor {index}',
        'investor_type': InvestorProfile.InvestorType.FUND,
        'investment_min': Decimal('1000.00'),
        'is_verified': True,
    }
    fields.update(overrides)
    return InvestorProfile.objects.create(**fields)


class InvestorListViewTest(APITestCase):
    def setUp(self):
        self.url = reverse('investors:investor-list')
        self.investors = [create_investor(index) for index in range(10)]

    def test_list_structure_and_default_page_size(self):
        """Verify GET /api/investors/ returns the paginated format, 8 per page."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), {'count', 'next', 'previous', 'results'})
        self.assertEqual(response.data['count'], 10)
        self.assertEqual(len(response.data['results']), 8)
        self.assertIsNotNone(response.data['next'])
        self.assertEqual(set(response.data['results'][0]), LIST_FIELDS)

    def test_second_page(self):
        """Verify the last page holds the remainder and has no next link."""
        response = self.client.get(self.url, {'page': 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['previous'])
        self.assertIsNone(response.data['next'])

    def test_page_size_param(self):
        """Verify page_size changes the number of items per page."""
        response = self.client.get(self.url, {'page_size': 3})

        self.assertEqual(len(response.data['results']), 3)

    def test_unverified_investor_is_excluded(self):
        """Verify unverified investors are neither listed nor counted."""
        hidden = create_investor(99, is_verified=False)

        response = self.client.get(self.url, {'page_size': 100})

        ids = [item['investor_id'] for item in response.data['results']]
        self.assertNotIn(hidden.investor_id, ids)
        self.assertEqual(response.data['count'], 10)

    def test_order_is_stable_and_ascending_by_id(self):
        """Verify the list is ordered by investor_id and repeatable."""
        first = self.client.get(self.url, {'page_size': 100})
        second = self.client.get(self.url, {'page_size': 100})

        ids = [item['investor_id'] for item in first.data['results']]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(first.data['results'], second.data['results'])

    def test_investment_min_formats(self):
        """Verify investment_min is a string with 2 decimals, or null."""
        InvestorProfile.objects.all().delete()
        create_investor(101, investment_min=Decimal('50000'))
        create_investor(102, investment_min=None)

        response = self.client.get(self.url)

        values = [item['investment_min'] for item in response.data['results']]
        self.assertEqual(values, ['50000.00', None])

    def test_public_access_without_authentication(self):
        """Verify the endpoint is available to anonymous clients."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_no_private_fields(self):
        """Verify private data never appears in list items."""
        response = self.client.get(self.url)

        self.assertFalse(PRIVATE_FIELDS & set(response.data['results'][0]))

    def test_non_get_methods_are_not_allowed(self):
        """Verify write methods are rejected with 405."""
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)

                self.assertEqual(
                    response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
                )


class InvestorListFilterTest(APITestCase):
    def setUp(self):
        self.url = reverse('investors:investor-list')
        self.green = create_investor(
            1, investor_name='Green Capital', investor_type='fund'
        )
        self.angels = create_investor(
            2, investor_name='Kyiv Angels', investor_type='private'
        )
        self.craft = create_investor(
            3, investor_name='Craft Ventures', investor_type='company'
        )
        self.green_corp = create_investor(
            4, investor_name='Greenfield Corp', investor_type='company'
        )
        self.hidden = create_investor(
            5, investor_name='Green Hidden', investor_type='fund', is_verified=False
        )

    def names(self, response):
        return [item['investor_name'] for item in response.data['results']]

    def test_search_by_name_is_case_insensitive(self):
        """Verify search returns only investors whose name contains the text."""
        response = self.client.get(self.url, {'search': 'gREEN'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.names(response), ['Green Capital', 'Greenfield Corp'])

    def test_search_does_not_reveal_unverified(self):
        """Verify an unverified investor is not found by search."""
        response = self.client.get(self.url, {'search': 'Hidden'})

        self.assertEqual(response.data['count'], 0)

    def test_search_without_matches(self):
        """Verify a search without matches gives an empty page, not an error."""
        response = self.client.get(self.url, {'search': 'zzz'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])

    def test_filter_by_type(self):
        """Verify the type filter returns only investors of that type."""
        response = self.client.get(self.url, {'type': 'company'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.names(response), ['Craft Ventures', 'Greenfield Corp'])
        for item in response.data['results']:
            self.assertEqual(item['investor_type'], 'company')

    def test_filter_by_each_valid_type(self):
        """Verify every documented type value is accepted."""
        for investor_type in ('private', 'fund', 'company'):
            with self.subTest(investor_type=investor_type):
                response = self.client.get(self.url, {'type': investor_type})

                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_search_and_type_combine(self):
        """Verify search and type narrow the result together."""
        response = self.client.get(self.url, {'search': 'green', 'type': 'company'})

        self.assertEqual(self.names(response), ['Greenfield Corp'])

    def test_unknown_type_returns_400_with_allowed_values(self):
        """Verify an unknown type is rejected and the valid values are listed."""
        response = self.client.get(self.url, {'type': 'unknown'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        message = str(response.data)
        for investor_type in ('private', 'fund', 'company'):
            self.assertIn(investor_type, message)

    def test_empty_type_returns_400(self):
        """Verify an empty type value is treated as unknown, not ignored."""
        response = self.client.get(self.url, {'type': ''})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_type_is_case_sensitive(self):
        """Verify only the exact lowercase codes are accepted."""
        response = self.client.get(self.url, {'type': 'FUND'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_page_returns_404(self):
        """Verify a page beyond the last one gives 404."""
        response = self.client.get(self.url, {'page': 99})

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_page_size_falls_back_to_default(self):
        """Verify a non-numeric or non-positive page_size does not cause an error."""
        for value in ('abc', '0', '-1'):
            with self.subTest(page_size=value):
                response = self.client.get(self.url, {'page_size': value})

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data['count'], 4)

    def test_page_size_is_capped(self):
        """Verify page_size larger than the maximum is limited to 100."""
        for index in range(10, 115):
            create_investor(index)

        response = self.client.get(self.url, {'page_size': 1000})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 100)


class InvestorDetailViewTest(APITestCase):
    def setUp(self):
        self.investor = create_investor(
            1,
            investor_name='Green Capital',
            investor_description='We invest in craft food and eco packaging.',
            investor_phone='+380501234567',
            edrpou_or_ipn='12345678',
            investment_min=Decimal('50000'),
        )
        self.url = reverse(
            'investors:investor-detail', kwargs={'id': self.investor.investor_id}
        )

    def test_detail_schema_and_values(self):
        """Verify GET /api/investors/{id}/ returns the documented public profile."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), DETAIL_FIELDS)
        self.assertEqual(
            response.data,
            {
                'investor_id': self.investor.investor_id,
                'investor_name': 'Green Capital',
                'investor_type': 'fund',
                'investor_description': 'We invest in craft food and eco packaging.',
                'contact': {'phone': '+380501234567'},
                'investment_min': '50000.00',
                'is_verified': True,
            },
        )

    def test_empty_phone_is_empty_string(self):
        """Verify a missing phone is returned as an empty string, not omitted."""
        self.investor.investor_phone = ''
        self.investor.save()

        response = self.client.get(self.url)

        self.assertEqual(response.data['contact'], {'phone': ''})

    def test_null_investment_min(self):
        """Verify a missing investment_min is returned as null."""
        self.investor.investment_min = None
        self.investor.save()

        response = self.client.get(self.url)

        self.assertIsNone(response.data['investment_min'])

    def test_no_private_fields(self):
        """Verify private data never appears in the profile."""
        response = self.client.get(self.url)

        self.assertFalse(PRIVATE_FIELDS & set(response.data))

    def test_public_access_without_authentication(self):
        """Verify the endpoint is available to anonymous clients."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unknown_id_returns_404(self):
        """Verify an unknown investor id gives 404."""
        url = reverse('investors:investor-detail', kwargs={'id': 999999})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unverified_investor_returns_same_404(self):
        """Verify an unverified investor is indistinguishable from an unknown one."""
        hidden = create_investor(2, is_verified=False)
        hidden_url = reverse(
            'investors:investor-detail', kwargs={'id': hidden.investor_id}
        )
        unknown_url = reverse('investors:investor-detail', kwargs={'id': 999999})

        hidden_response = self.client.get(hidden_url)
        unknown_response = self.client.get(unknown_url)

        self.assertEqual(hidden_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(hidden_response.data, unknown_response.data)

    def test_non_get_methods_are_not_allowed(self):
        """Verify write methods are rejected with 405."""
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)

                self.assertEqual(
                    response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
                )


class InvestorFixtureTest(TestCase):
    def test_fixture_loads(self):
        """Verify the sample fixture loads and has verified and unverified rows."""
        call_command('loaddata', 'investors', verbosity=0)

        verified = InvestorProfile.objects.filter(is_verified=True)
        self.assertGreaterEqual(verified.count(), 2)
        self.assertTrue(InvestorProfile.objects.filter(is_verified=False).exists())
        self.assertTrue(verified.filter(investment_min__isnull=True).exists())
        self.assertTrue(verified.filter(investor_phone='').exists())
