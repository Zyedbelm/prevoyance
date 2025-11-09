"""Moteur de calcul pour les projections de prévoyance retraite suisse.

Ce module expose la classe `CalculateurPrevoyance` qui réalise l'ensemble des
calculs financiers décrits dans le script initial fourni par l'utilisateur.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ResultatPrevoyance:
    """Stocke les résultats détaillés de la simulation."""

    capital_3a_nominal: float
    capital_sp500_nominal: float
    capital_lpp_nominal: float
    capital_total_nominal: float
    capital_3a_reel: float
    capital_sp500_reel: float
    capital_lpp_reel: float
    capital_total_reel: float
    versements_totaux_3a: float
    versements_totaux_sp500: float
    cotisations_totales_lpp: float
    cotisations_employe_lpp: float
    cotisations_employeur_lpp: float
    detail_annuel: List[dict]
    annee_retrait: Optional[int] = None
    montant_retrait_immo: float = 0.0


class CalculateurPrevoyance:
    """Calculateur de prévoyance retraite suisse avec taux LPP fixes."""

    def __init__(
        self,
        age_depart: int,
        age_retraite: int,
        salaire_brut_initial: float,
        lpp_capital_initial: float,
        evolution_salaire_annuel: float,
        montant_mensuel_3a: float,
        rendement_3a: float,
        montant_mensuel_sp500: float,
        rendement_sp500: float,
        taux_imposition_dividendes: float,
        rendement_lpp: float,
        inflation_annuelle: float,
        taux_cotisation_employe_lpp_paliers: Dict[str, float],
        taux_cotisation_employeur_lpp_paliers: Dict[str, float],
        montant_coordination: float,
        salaire_coordonne_max: float = 88_200,
        couvrir_surobligatoire: bool = False,
        taux_dividendes_sp500: float = 2.0,
    ) -> None:
        """Initialise le calculateur avec les paramètres de simulation."""

        self.age_depart = age_depart
        self.age_retraite = age_retraite
        self.annees = age_retraite - age_depart
        self.salaire_brut_initial = salaire_brut_initial
        self.lpp_capital_initial = lpp_capital_initial
        self.evolution_salaire = evolution_salaire_annuel / 100
        self.montant_mensuel_3a = montant_mensuel_3a
        self.rendement_3a = rendement_3a / 100
        self.montant_mensuel_sp500 = montant_mensuel_sp500
        self.rendement_sp500_brut = rendement_sp500 / 100
        self.taux_imposition = taux_imposition_dividendes / 100
        self.rendement_lpp = rendement_lpp / 100
        self.inflation = inflation_annuelle / 100
        self.montant_coordination = montant_coordination
        self.salaire_coordonne_max = salaire_coordonne_max
        self.couvrir_surobligatoire = couvrir_surobligatoire
        self.taux_dividendes_sp500 = taux_dividendes_sp500 / 100

        self.taux_employe_lpp_paliers = {
            "moins_30": taux_cotisation_employe_lpp_paliers.get("moins_30", 7.0) / 100,
            "30_39": taux_cotisation_employe_lpp_paliers.get("30_39", 10.0) / 100,
            "40_49": taux_cotisation_employe_lpp_paliers.get("40_49", 15.0) / 100,
            "50_plus": taux_cotisation_employe_lpp_paliers.get("50_plus", 18.0) / 100,
        }
        self.taux_employeur_lpp_paliers = {
            "moins_30": taux_cotisation_employeur_lpp_paliers.get("moins_30", 8.0) / 100,
            "30_39": taux_cotisation_employeur_lpp_paliers.get("30_39", 11.0) / 100,
            "40_49": taux_cotisation_employeur_lpp_paliers.get("40_49", 16.0) / 100,
            "50_plus": taux_cotisation_employeur_lpp_paliers.get("50_plus", 19.0) / 100,
        }

        impot_dividendes = self.taux_dividendes_sp500 * self.taux_imposition
        self.rendement_sp500_net = self.rendement_sp500_brut - impot_dividendes
        self.rendement_lpp_mensuel = (1 + self.rendement_lpp) ** (1 / 12) - 1

    def _taux_palier(self, age: int, mapping: Dict[str, float]) -> float:
        """Retourne le taux applicable selon l'âge."""

        if age < 30:
            return mapping["moins_30"]
        if age < 40:
            return mapping["30_39"]
        if age < 50:
            return mapping["40_49"]
        return mapping["50_plus"]

    def calculer_3a(self, annee_retrait: Optional[int] = None) -> tuple:
        """Calcule le capital du 3ème pilier A avec intérêts composés mensuels."""

        capital = 0.0
        versements_totaux = 0.0
        detail = []
        taux_mensuel = (1 + self.rendement_3a) ** (1 / 12) - 1

        for annee in range(1, self.annees + 1):
            age = self.age_depart + annee
            retrait_immobilier = None

            for _ in range(12):
                capital = capital * (1 + taux_mensuel) + self.montant_mensuel_3a
                versements_totaux += self.montant_mensuel_3a

            if annee_retrait is not None and annee == annee_retrait:
                retrait_immobilier = capital
                capital = 0.0

            detail.append(
                {
                    "annee": annee,
                    "age": age,
                    "capital_3a": capital,
                    "versements_annee": self.montant_mensuel_3a * 12,
                    "retrait_immobilier": retrait_immobilier,
                }
            )

        return capital, versements_totaux, detail

    def calculer_sp500(self, annee_retrait: Optional[int] = None) -> tuple:
        """Calcule le capital investi dans le SP500 avec rendement net."""

        capital = 0.0
        versements_totaux = 0.0
        detail = []
        taux_mensuel = (1 + self.rendement_sp500_net) ** (1 / 12) - 1

        for annee in range(1, self.annees + 1):
            age = self.age_depart + annee
            for _ in range(12):
                capital = capital * (1 + taux_mensuel) + self.montant_mensuel_sp500
                versements_totaux += self.montant_mensuel_sp500

            detail.append(
                {
                    "annee": annee,
                    "age": age,
                    "capital_sp500": capital,
                    "versements_annee": self.montant_mensuel_sp500 * 12,
                }
            )

        return capital, versements_totaux, detail

    def calculer_lpp(self, annee_retrait: Optional[int] = None) -> tuple:
        """Calcule le capital LPP avec taux fixes et évolution salariale."""

        capital = self.lpp_capital_initial
        cotisations_totales = 0.0
        cotisations_employe_totales = 0.0
        cotisations_employeur_totales = 0.0
        detail = []

        for annee in range(1, self.annees + 1):
            age = self.age_depart + annee
            salaire_annee = self.salaire_brut_initial * ((1 + self.evolution_salaire) ** annee)
            salaire_coordonne = max(0.0, salaire_annee - self.montant_coordination)
            if self.couvrir_surobligatoire:
                salaire_assure = salaire_coordonne
            else:
                salaire_assure = min(salaire_coordonne, self.salaire_coordonne_max)

            taux_employe = self._taux_palier(age, self.taux_employe_lpp_paliers)
            taux_employeur = self._taux_palier(age, self.taux_employeur_lpp_paliers)

            cotisation_employe_annuelle = salaire_assure * taux_employe
            cotisation_employeur_annuelle = salaire_assure * taux_employeur
            cotisation_annuelle = cotisation_employe_annuelle + cotisation_employeur_annuelle

            cotisation_mensuelle_employe = cotisation_employe_annuelle / 12
            cotisation_mensuelle_employeur = cotisation_employeur_annuelle / 12
            cotisation_mensuelle_totale = cotisation_annuelle / 12
            retrait_immobilier = None

            for _ in range(12):
                capital = capital * (1 + self.rendement_lpp_mensuel)
                capital += cotisation_mensuelle_totale

            if annee_retrait is not None and annee == annee_retrait:
                retrait_immobilier = capital
                capital = 0.0

            cotisations_totales += cotisation_annuelle
            cotisations_employe_totales += cotisation_employe_annuelle
            cotisations_employeur_totales += cotisation_employeur_annuelle

            detail.append(
                {
                    "annee": annee,
                    "age": age,
                    "salaire_brut": salaire_annee,
                    "salaire_coordonne": salaire_assure,
                    "taux_employe": taux_employe * 100,
                    "taux_employeur": taux_employeur * 100,
                    "taux_total": (taux_employe + taux_employeur) * 100,
                    "cotisation_employe": cotisation_employe_annuelle,
                    "cotisation_employeur": cotisation_employeur_annuelle,
                    "cotisation_totale": cotisation_annuelle,
                    "capital_lpp": capital,
                    "retrait_immobilier": retrait_immobilier,
                }
            )

        return (
            capital,
            cotisations_totales,
            cotisations_employe_totales,
            cotisations_employeur_totales,
            detail,
        )

    def ajuster_inflation(self, montant: float) -> float:
        """Ajuste un montant nominal en pouvoir d'achat réel."""

        facteur_erosion = (1 + self.inflation) ** self.annees
        return montant / facteur_erosion

    def calculer(self, annee_retrait: Optional[int] = None) -> ResultatPrevoyance:
        """Calcule l'ensemble de la prévoyance."""

        capital_3a, versements_3a, detail_3a = self.calculer_3a(annee_retrait=annee_retrait)
        capital_sp500, versements_sp500, detail_sp500 = self.calculer_sp500(annee_retrait=annee_retrait)
        (
            capital_lpp,
            cotisations_lpp,
            cotisations_employe_lpp,
            cotisations_employeur_lpp,
            detail_lpp,
        ) = self.calculer_lpp(annee_retrait=annee_retrait)

        capital_total_nominal = capital_3a + capital_sp500 + capital_lpp

        capital_3a_reel = self.ajuster_inflation(capital_3a)
        capital_sp500_reel = self.ajuster_inflation(capital_sp500)
        capital_lpp_reel = self.ajuster_inflation(capital_lpp)
        capital_total_reel = capital_3a_reel + capital_sp500_reel + capital_lpp_reel

        detail_annuel = []
        montant_retrait_immo = 0.0
        for i in range(self.annees):
            retrait_3a = detail_3a[i].get("retrait_immobilier")
            retrait_lpp = detail_lpp[i].get("retrait_immobilier")
            if annee_retrait is not None and i + 1 == annee_retrait:
                montant_retrait_immo = sum(
                    filter(
                        None,
                        [retrait_3a, retrait_lpp],
                    )
                )

            entree = {
                **detail_lpp[i],
                "capital_3a": detail_3a[i]["capital_3a"],
                "capital_sp500": detail_sp500[i]["capital_sp500"],
                "capital_total": detail_lpp[i]["capital_lpp"]
                + detail_3a[i]["capital_3a"]
                + detail_sp500[i]["capital_sp500"],
            }
            if annee_retrait is not None and i + 1 == annee_retrait:
                entree["retrait_immo_total"] = montant_retrait_immo
            detail_annuel.append(entree)

        return ResultatPrevoyance(
            capital_3a_nominal=capital_3a,
            capital_sp500_nominal=capital_sp500,
            capital_lpp_nominal=capital_lpp,
            capital_total_nominal=capital_total_nominal,
            capital_3a_reel=capital_3a_reel,
            capital_sp500_reel=capital_sp500_reel,
            capital_lpp_reel=capital_lpp_reel,
            capital_total_reel=capital_total_reel,
            versements_totaux_3a=versements_3a,
            versements_totaux_sp500=versements_sp500,
            cotisations_totales_lpp=cotisations_lpp,
            cotisations_employe_lpp=cotisations_employe_lpp,
            cotisations_employeur_lpp=cotisations_employeur_lpp,
            detail_annuel=detail_annuel,
            annee_retrait=annee_retrait,
            montant_retrait_immo=montant_retrait_immo,
        )


