from django.shortcuts import redirect
from django.views.generic import TemplateView


class LandingView(TemplateView):
    template_name = 'landing.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('field_list')
        return super().dispatch(request, *args, **kwargs)

