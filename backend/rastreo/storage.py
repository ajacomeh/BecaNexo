"""Archivo privado por contenido. No elimina huérfanos ni repara originales."""
import hashlib
import os
import tempfile
from pathlib import Path
from django.conf import settings
from .models import Documento


class StorageError(Exception):
    pass


def root_path():
    value = settings.RASTREO_STORAGE_ROOT
    if not value or not Path(value).is_absolute():
        raise StorageError('Configure RASTREO_STORAGE_ROOT como ruta absoluta privada.')
    root = Path(value).resolve()
    repo = Path(settings.BASE_DIR).resolve().parent
    if root == repo or root.is_relative_to(repo):
        raise StorageError('El archivo documental debe estar fuera del repositorio.')
    if not root.is_dir():
        raise StorageError('La carpeta documental no existe; crear/configurar explícitamente.')
    return root


def key_for(digest):
    return f'{digest[:2]}/{digest}.bin'


def verify_file(path, digest, size):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
        raise StorageError('Archivo ausente o tamaño/tipo diferente; no se reemplaza.')
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise StorageError('Huella del archivo diferente; no se reemplaza.')


def prepare_document(content, mime):
    mime = mime.split(';')[0].strip().lower()
    limits = {'application/pdf': 8388608, 'text/html': 2097152, 'text/plain': 2097152}
    if mime not in limits or not isinstance(content, bytes) or len(content) > limits[mime]:
        raise StorageError('MIME o tamaño no permitido.')
    if mime == 'application/pdf' and not content.startswith(b'%PDF-'):
        raise StorageError('Firma PDF inválida.')
    if mime.startswith('text/'):
        try:
            text = content.decode('utf-8-sig')
        except UnicodeError as exc:
            raise StorageError('Texto no UTF-8.') from exc
        if '\x00' in text or (mime == 'text/html' and '<' not in text):
            raise StorageError('Contenido no corresponde al MIME de texto.')
    root = root_path()
    digest = hashlib.sha256(content).hexdigest()
    key = key_for(digest)
    path = root / key
    path.parent.mkdir(exist_ok=True)
    if path.parent.is_symlink() or path.parent.resolve().parent != root:
        raise StorageError('Ruta documental insegura.')
    if path.exists():
        verify_file(path, digest, len(content))
        if path.read_bytes() != content:
            raise StorageError('Colisión documental; no reemplazar.')
    else:
        # Mismo volumen: hard link crea el nombre final atómicamente SIN reemplazo.
        # Si el proceso cae, el temporal queda inventariado, no se limpia solo.
        fd, temporary = tempfile.mkstemp(prefix='.pendiente-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                verify_file(path, digest, len(content))
                if path.read_bytes() != content:
                    raise StorageError('Colisión documental.')
            # Solo temporal propio ya finalizado, nunca evidencia previa.
            os.unlink(temporary)
        except OSError as exc:
            raise StorageError('Fallo de almacenamiento; temporal conservado para inspección.') from exc
    verify_file(path, digest, len(content))
    return {'sha256': digest, 'tamano_bytes': len(content), 'mime': mime, 'clave_almacenamiento': key}


def register_document(prepared):
    values = dict(prepared)
    digest = values.pop('sha256')
    document, created = Documento.objects.get_or_create(sha256=digest, defaults=values)
    if any(getattr(document, field) != value for field, value in values.items()):
        raise StorageError('Metadatos documentales inconsistentes.')
    return document, created


def save_document(content, mime):
    return register_document(prepare_document(content, mime))


def integrity_report():
    root = root_path()
    expected, problems = set(), []
    for doc in Documento.objects.iterator():
        expected.add(doc.clave_almacenamiento)
        if doc.clave_almacenamiento != key_for(doc.sha256):
            problems.append({'documento': doc.pk, 'problema': 'clave_invalida'})
            continue
        try:
            path = root / doc.clave_almacenamiento
            if path.parent.is_symlink():
                raise StorageError('Directorio enlazado.')
            verify_file(path, doc.sha256, doc.tamano_bytes)
        except (StorageError, OSError):
            problems.append({'documento': doc.pk, 'problema': 'ausente_o_corrupto'})
    for path in root.rglob('*'):
        if path.is_file() and path.relative_to(root).as_posix() not in expected:
            problems.append({'archivo': path.relative_to(root).as_posix(), 'problema': 'sin_referencia'})
    return {'documentos': len(expected), 'problemas': problems, 'eliminados': 0}
