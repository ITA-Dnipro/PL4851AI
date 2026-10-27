from django.urls import path

from investors.views import InvestorProfileListView, InvestorPublicProfileDetailView

app_name = 'investors'

urlpatterns = [
    path('', InvestorProfileListView.as_view(), name='investor-list'),
    path(
        '<int:id>/',
        InvestorPublicProfileDetailView.as_view(),
        name='investor-detail',
    ),
]
