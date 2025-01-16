from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect


class AuthMiddleWare(MiddlewareMixin):
    def process_request(self, request):
        if not request.path_info in ['/login/', '/image/get/']:
            session_info = request.session.get('identification')
            if not session_info:
                return redirect('swinTransformer:login')
