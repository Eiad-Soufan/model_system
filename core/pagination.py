from rest_framework.pagination import PageNumberPagination

class StandardResultsSetPagination(PageNumberPagination):
    """Page-number pagination with safe defaults.
    - Default page size: 10
    - Client can override with ?page_size=... up to max_page_size.
    """
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100
