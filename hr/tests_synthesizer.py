from django.test import SimpleTestCase

from hr.assistant.synthesizer import synthesize_adapted_answer


class SynthesizerTests(SimpleTestCase):
    def test_adapts_horaires_question_without_raw_source_prefix(self):
        rag = (
            "[reglement_interieur.txt]\n"
            "RÈGLEMENT INTÉRIEUR – ENTREPRISE LAITIÈRE PeopleFlow\n"
            "HORAIRES DE TRAVAIL\n"
            "- Production et logistique : postes en 3×8 (06h-14h, 14h-22h, 22h-06h).\n"
            "- Bureaux (RH, commercial, finance) : 08h30 – 17h30 du lundi au vendredi."
        )
        answer = synthesize_adapted_answer(
            "Quels sont les horaires de travail en bureau ?",
            rag_text=rag,
            sources=["reglement_interieur.txt"],
        )

        self.assertIn("08h30", answer)
        self.assertNotIn("[reglement_interieur.txt]", answer)
        self.assertIn("horaires", answer.lower())

    def test_adapts_conges_question(self):
        rag = (
            "[reglement_interieur.txt]\n"
            "CONGÉS ET ABSENCES\n"
            "- Toute absence doit faire l'objet d'une demande via PeopleFlow.\n"
            "- Congé annuel : 18 jours ouvrés par an."
        )
        answer = synthesize_adapted_answer(
            "Comment demander un congé ?",
            rag_text=rag,
            sources=["reglement_interieur.txt"],
        )

        self.assertIn("congé", answer.lower())
        self.assertIn("18 jours", answer)
