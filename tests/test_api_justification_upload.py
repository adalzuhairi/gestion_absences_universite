from datetime import date, time

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.absences.models import Absence, Justification
from apps.academic_sessions.models import AnneeAcademique, Seance
from apps.academics.models import Cours, Departement, Faculte
from apps.accounts.models import User
from apps.enrollments.models import Inscription

URL = "/api/v1/justifications/"
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class ApiJustificationUploadTests(TestCase):
    """POST /api/v1/justifications/ applies the same file rules as the web form."""

    def setUp(self):
        self.student = User.objects.create_user(
            email="upload-api@example.com",
            nom="Upload",
            prenom="Api",
            password="pass1234",
            role=User.Role.ETUDIANT,
        )
        faculte = Faculte.objects.create(nom_faculte="Faculte Upload")
        dept = Departement.objects.create(nom_departement="Dept", id_faculte=faculte)
        annee = AnneeAcademique.objects.create(libelle="2026-2027", active=True)
        cours = Cours.objects.create(
            code_cours="UPL101",
            nom_cours="Upload",
            nombre_total_periodes=30,
            id_departement=dept,
            id_annee=annee,
            niveau=1,
        )
        seance = Seance.objects.create(
            id_cours=cours,
            id_annee=annee,
            date_seance=date(2026, 10, 1),
            heure_debut=time(8),
            heure_fin=time(10),
        )
        inscription = Inscription.objects.create(
            id_etudiant=self.student, id_cours=cours, id_annee=annee
        )
        self.absence = Absence.objects.create(
            id_inscription=inscription,
            id_seance=seance,
            type_absence=Absence.TypeAbsence.ABSENT,
            duree_absence=2,
            statut=Absence.Statut.NON_JUSTIFIEE,
            encodee_par=self.student,
        )
        self.client = APIClient()
        self.client.defaults.update(
            {"wsgi.url_scheme": "https", "HTTP_X_FORWARDED_PROTO": "https"}
        )
        self.client.force_authenticate(self.student)

    def post(self, document=None):
        data = {"id_absence": self.absence.pk, "commentaire": "test"}
        if document is not None:
            data["document"] = document
        return self.client.post(URL, data, format="multipart")

    def test_valid_pdf_is_accepted_and_renamed(self):
        response = self.post(
            SimpleUploadedFile("certificat.pdf", PDF, content_type="application/pdf")
        )
        self.assertEqual(response.status_code, 201, response.content)
        justification = Justification.objects.get(id_absence=self.absence)
        self.assertTrue(justification.document.name.endswith(".pdf"))
        self.assertNotIn("certificat", justification.document.name)
        justification.document.delete(save=False)

    def test_missing_document_is_rejected(self):
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("document", response.json())

    def test_forbidden_extension_is_rejected(self):
        response = self.post(
            SimpleUploadedFile(
                "virus.exe", b"MZ\x90\x00", content_type="application/octet-stream"
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("document", response.json())
        self.assertFalse(Justification.objects.exists())

    def test_spoofed_pdf_signature_is_rejected(self):
        response = self.post(
            SimpleUploadedFile(
                "page.pdf", b"<html><script>x</script></html>", content_type="application/pdf"
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("document", response.json())
