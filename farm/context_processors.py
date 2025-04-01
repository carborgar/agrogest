def sidebar_state(request):
    return {
        'sidebar_collapsed': request.COOKIES.get('sidebar_collapsed', 'false') == 'true'
    }
