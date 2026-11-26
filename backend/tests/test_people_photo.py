"""Student photos: upload (JPG/PNG only), view with record visibility, remove."""
import io

from django.core.files.uploadedfile import SimpleUploadedFile

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")


def test_photo_upload_view_and_remove(client_for, make_user, make_student, school, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = client_for(make_user("adm@s.edu", "inst_admin", school))
    student = make_student(school)
    url = f"/api/students/{student.id}/photo/"

    assert admin.get(url).status_code == 404  # none yet
    fake = SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", content_type="image/png")
    bad = admin.post(url, {"photo": fake}, format="multipart")
    assert bad.status_code == 400 and "photo" in bad.data["fields"]

    ok = admin.post(url, {"photo": SimpleUploadedFile("me.png", PNG, content_type="image/png")}, format="multipart")
    assert ok.status_code == 200 and ok.data["photo_url"].startswith(url)
    got = admin.get(url)
    assert got.status_code == 200 and got["Content-Type"] == "image/png"
    assert b"".join(got.streaming_content) == PNG

    # Someone who cannot see the student cannot see the photo either; teachers cannot change it.
    outsider = client_for(make_user("t@s.edu", "subject_teacher", school))
    assert outsider.get(url).status_code == 404
    assert outsider.post(url, {"photo": SimpleUploadedFile("x.png", PNG)}, format="multipart").status_code == 403

    assert admin.delete(url).status_code == 204
    assert admin.get(f"/api/students/{student.id}/").data["photo_url"] is None
