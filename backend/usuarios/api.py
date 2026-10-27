from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Usuario
from .serializers import LoginSerializer, RegistroSerializer, UsuarioSerializer, NombreSerializer
from .throttles import LoginThrottle, RegistroThrottle


class CSRFSesionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        # También verifica solicitudes anónimas: SessionAuthentication sola no lo hace.
        self.enforce_csrf(request)
        return super().authenticate(request)


@method_decorator(never_cache, name="dispatch")
class AuthView(APIView):
    authentication_classes = [CSRFSesionAuthentication]
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]


class CSRFView(AuthView):
    http_method_names = ["get", "options"]

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class RegistroView(AuthView):
    http_method_names = ["post", "options"]
    throttle_classes = [RegistroThrottle]

    def post(self, request):
        serializer = RegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                user = Usuario.objects.create_user(**serializer.validated_data)
        except IntegrityError as exc:
            # PostgreSQL resuelve también carreras entre registros simultáneos.
            if getattr(exc.__cause__, "sqlstate", None) != "23505":
                raise
            return Response({"email": ["No se puede registrar este correo."]}, status=400)
        return Response(UsuarioSerializer(user).data, status=201)


class LoginView(AuthView):
    http_method_names = ["post", "options"]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request=request, **serializer.validated_data)
        if user is None:
            return Response({"detail": "Correo o contraseña incorrectos."}, status=400)
        login(request, user)
        return Response({"usuario": UsuarioSerializer(user).data, "csrfToken": get_token(request)})


class MeView(AuthView):
    http_method_names = ["get", "patch", "options"]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)

    def patch(self, request):
        if request.query_params:
            return Response({"detail": "Esta operación no acepta parámetros de consulta."}, status=400)
        serializer = NombreSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.nombre = serializer.validated_data["nombre"]
        user.save(update_fields=["nombre"])
        return Response({"nombre": user.nombre})


class LogoutView(AuthView):
    http_method_names = ["post", "options"]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=204)
