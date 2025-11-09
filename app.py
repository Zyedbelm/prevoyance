"""Application Streamlit locale de projection de prévoyance retraite.

L'application reprend la logique de calcul fournie par l'utilisateur et
propose une interface pédagogique indiquant les hypothèses et fourchettes
raisonnables basées sur des sources publiques (OFAS, FINMA, données marché).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import pandas as pd
import streamlit as st

from prevoyance import CalculateurPrevoyance


st.set_page_config(
    page_title="Projection prévoyance suisse",
    page_icon="💎",
    layout="wide",
)


def formater_chf(valeur: float) -> str:
    """Formatte un montant en francs suisses."""

    return f"CHF {valeur:,.0f}".replace(",", " ")


def afficher_contextualisation() -> None:
    """Affiche les explications des données d'entrée et des calculs."""

    st.sidebar.header("ℹ️ Aide au paramétrage")
    st.sidebar.markdown(
        """
        - **Âges** : la retraite AVS s'établit à 65 ans pour les hommes et
          passera progressivement à 65 ans pour les femmes (réforme AVS 21).
        - **Salaire brut** : salaire annuel soumis à la LPP. La déduction de
          coordination 2024 est de **CHF 25 725** (source : [OFAS](https://www.ofas.admin.ch)).
        - **3ᵉ pilier A** : le plafond 2024 pour salariés affiliés à une caisse
          de pension est **CHF 7 056/an** soit **CHF 588/mois** (source :
          [ESTV](https://www.estv.admin.ch)).
        - **Rendements** : historiques moyens (1988-2023) :
          S&P 500 ~10 % brut avec ~2 % de dividendes, chômage en Suisse ~2 %.
        - **Inflation** : moyenne suisse 1993-2023 ~0,9 %, mais 2022-2023 ~2 %.
          Ajustez selon votre anticipation.
        """
    )

    st.sidebar.markdown(
        """
        ### Méthodologie
        - Capitalisation mensuelle des versements pour le 3ᵉ pilier et l'indice.
        - Cotisations LPP calculées sur le salaire coordonné avec capitalisation
          annuelle.
        - Pouvoir d'achat ajusté via l'inflation composée.
        - Dividendes S&P 500 imposés au taux marginal indiqué.
        """
    )

    with st.expander("Comment sont effectués les calculs ?", expanded=False):
        st.markdown(
            """
            1. **3ᵉ pilier A** : application d'un rendement annuel net, composé
               mensuellement sur les versements.
            2. **Investissement indiciel** : rendement brut moins l'impôt sur
               dividendes, composé mensuellement.
            3. **LPP** : évolution du salaire selon votre hypothèse, calcul du
               salaire coordonné, application des taux de cotisation fixes et
               capitalisation annuelle avec un rendement net.
            4. **Inflation** : conversion des capitaux nominaux vers des montants
               réels via un facteur d'érosion du pouvoir d'achat.
            5. **Rente LPP** : estimation via un taux de conversion standard de
               5,5 % (moyenne des caisses suisses en 2024 selon l'ASIP).
            """
        )


def saisir_parametres_personne(prefix: str, titre: str, defaults: Dict[str, float]) -> Dict[str, float]:
    """Construit l'interface de saisie pour un profil donné (principal ou partenaire)."""

    st.markdown(f"### {titre}")

    col_age, col_retraite, col_inflation = st.columns(3)
    age_depart = col_age.number_input(
        "Âge actuel",
        min_value=18,
        max_value=64,
        value=int(defaults["age_depart"]),
        help="Âge légal minimal LPP : 18 ans.",
        key=f"{prefix}_age_depart",
    )
    age_retraite = col_retraite.number_input(
        "Âge de retraite",
        min_value=age_depart + 1,
        max_value=70,
        value=int(defaults["age_retraite"]),
        help="Âge cible (réforme AVS 21 : 65 ans).",
        key=f"{prefix}_age_retraite",
    )
    inflation_annuelle = col_inflation.slider(
        "Inflation annuelle anticipée",
        min_value=0.0,
        max_value=4.0,
        value=float(defaults["inflation"]),
        step=0.1,
        help="Inflation moyenne suisse 1993-2023 : 0,9 %. 2022-2023 : ~2,3 %.",
        key=f"{prefix}_inflation",
    )

    st.markdown("#### Paramètres essentiels")
    bloc_lpp, bloc_3a, bloc_sp500 = st.columns([1.5, 1, 1])

    with bloc_lpp:
        with st.container(border=True):
            st.subheader("Salaire & LPP")
            salaire_brut_initial = st.number_input(
                "Salaire brut annuel",
                min_value=30_000,
                max_value=300_000,
                value=float(defaults["salaire"]),
                step=1_000,
                help="Salaire soumis à la LPP (source : Salarium OFS).",
                key=f"{prefix}_salaire",
            )
            evolution_salaire_annuel = st.slider(
                "Évolution salariale annuelle",
                min_value=-2.0,
                max_value=5.0,
                value=float(defaults["evol_salaire"]),
                step=0.1,
                help="Hypothèse de progression salariale réelle (OFS : +1,5 % moyen).",
                key=f"{prefix}_evol_salaire",
            )
            rendement_lpp = st.slider(
                "Rendement annuel LPP",
                min_value=0.5,
                max_value=3.5,
                value=float(defaults["rendement_lpp"]),
                step=0.1,
                help="Taux d'intérêt minimum 2024 : 1,25 %. Moyenne caisse : ~2,1 %.",
                key=f"{prefix}_rendement_lpp",
            )
            montant_coordination = st.number_input(
                "Montant de coordination",
                min_value=0,
                max_value=40_000,
                value=float(defaults["coordination"]),
                step=25,
                help="Déduction légale LPP 2024 : CHF 25 725 (OFAS).",
                key=f"{prefix}_coordination",
            )
            lpp_capital_initial = st.number_input(
                "Capital LPP existant",
                min_value=0,
                max_value=2_000_000,
                value=float(defaults["capital_lpp"]),
                step=1_000,
                key=f"{prefix}_capital_lpp",
            )
            col_plafond, col_suroblig = st.columns([2, 1])
            salaire_coordonne_max = col_plafond.number_input(
                "Salaire annuel maximum assuré LPP",
                min_value=0,
                max_value=120_000,
                value=float(defaults["plafond"]),
                step=1_000,
                help="Plafond obligatoire 2024 : CHF 88 200.",
                key=f"{prefix}_plafond",
            )
            couvrir_surobligatoire = col_suroblig.checkbox(
                "Inclure la partie surobligatoire",
                value=bool(defaults["suroblig"]),
                help="Cochez pour couvrir la tranche surobligatoire (au-delà du plafond).",
                key=f"{prefix}_suroblig",
            )

            st.caption("Taux de cotisation par tranche d'âge (part employé)")
            cols_emp = st.columns(4)
            taux_cotisation_employe_lpp_paliers = {
                "moins_30": cols_emp[0].slider(
                    "Employé < 30 ans",
                    min_value=4.0,
                    max_value=12.0,
                    value=float(defaults["taux_emp_paliers"]["moins_30"]),
                    step=0.1,
                    key=f"{prefix}_taux_emp_moins_30",
                ),
                "30_39": cols_emp[1].slider(
                    "Employé 30-39 ans",
                    min_value=5.0,
                    max_value=15.0,
                    value=float(defaults["taux_emp_paliers"]["30_39"]),
                    step=0.1,
                    key=f"{prefix}_taux_emp_30_39",
                ),
                "40_49": cols_emp[2].slider(
                    "Employé 40-49 ans",
                    min_value=6.0,
                    max_value=18.0,
                    value=float(defaults["taux_emp_paliers"]["40_49"]),
                    step=0.1,
                    key=f"{prefix}_taux_emp_40_49",
                ),
                "50_plus": cols_emp[3].slider(
                    "Employé 50+ ans",
                    min_value=8.0,
                    max_value=20.0,
                    value=float(defaults["taux_emp_paliers"]["50_plus"]),
                    step=0.1,
                    key=f"{prefix}_taux_emp_50_plus",
                ),
            }

            st.caption("Taux de cotisation par tranche d'âge (part employeur)")
            cols_empres = st.columns(4)
            taux_cotisation_employeur_lpp_paliers = {
                "moins_30": cols_empres[0].slider(
                    "Employeur < 30 ans",
                    min_value=4.0,
                    max_value=15.0,
                    value=float(defaults["taux_empres_paliers"]["moins_30"]),
                    step=0.1,
                    key=f"{prefix}_taux_empres_moins_30",
                ),
                "30_39": cols_empres[1].slider(
                    "Employeur 30-39 ans",
                    min_value=5.0,
                    max_value=18.0,
                    value=float(defaults["taux_empres_paliers"]["30_39"]),
                    step=0.1,
                    key=f"{prefix}_taux_empres_30_39",
                ),
                "40_49": cols_empres[2].slider(
                    "Employeur 40-49 ans",
                    min_value=6.0,
                    max_value=20.0,
                    value=float(defaults["taux_empres_paliers"]["40_49"]),
                    step=0.1,
                    key=f"{prefix}_taux_empres_40_49",
                ),
                "50_plus": cols_empres[3].slider(
                    "Employeur 50+ ans",
                    min_value=8.0,
                    max_value=22.0,
                    value=float(defaults["taux_empres_paliers"]["50_plus"]),
                    step=0.1,
                    key=f"{prefix}_taux_empres_50_plus",
                ),
            }

    with bloc_3a:
        with st.container(border=True):
            st.subheader("3ᵉ pilier A")
            montant_mensuel_3a = st.slider(
                "Versement mensuel",
                min_value=0,
                max_value=600,
                value=int(defaults["montant_3a"]),
                step=10,
                help="Plafond 2024 salariés : CHF 588/mois (ESTV).",
                key=f"{prefix}_montant_3a",
            )
            rendement_3a = st.slider(
                "Rendement annuel",
                min_value=0.5,
                max_value=4.0,
                value=float(defaults["rendement_3a"]),
                step=0.1,
                help="Banques suisses : 1,0 %-2,5 % (Moneyland 2024).",
                key=f"{prefix}_rendement_3a",
            )

    with bloc_sp500:
        with st.container(border=True):
            st.subheader("Investissement S&P 500")
            montant_mensuel_sp500 = st.slider(
                "Versement mensuel",
                min_value=0,
                max_value=2_000,
                value=int(defaults["montant_sp500"]),
                step=50,
                help="Adapter selon votre capacité d'épargne.",
                key=f"{prefix}_montant_sp500",
            )
            rendement_sp500 = st.slider(
                "Rendement brut annuel",
                min_value=4.0,
                max_value=12.0,
                value=float(defaults["rendement_sp500"]),
                step=0.5,
                help="Retour moyen 1926-2023 ~10 % (Morningstar).",
                key=f"{prefix}_rendement_sp500",
            )
            taux_dividendes_sp500 = st.slider(
                "Taux de dividendes",
                min_value=1.0,
                max_value=3.0,
                value=float(defaults["dividendes_sp500"]),
                step=0.1,
                help="Rendement dividendes SP500 10 ans : 1,7 %-2,2 %.",
                key=f"{prefix}_dividendes_sp500",
            )
            taux_imposition_dividendes = st.slider(
                "Taux d'imposition marginal sur dividendes",
                min_value=0.0,
                max_value=40.0,
                value=float(defaults["taux_imposition_dividendes"]),
                step=1.0,
                help="Inclure impôt fédéral, cantonal et communal (ESTV).",
                key=f"{prefix}_imposition_dividendes",
            )

    return {
        "age_depart": int(age_depart),
        "age_retraite": int(age_retraite),
        "inflation_annuelle": float(inflation_annuelle),
        "salaire_brut_initial": float(salaire_brut_initial),
        "evolution_salaire_annuel": float(evolution_salaire_annuel),
        "rendement_lpp": float(rendement_lpp),
        "montant_coordination": float(montant_coordination),
        "lpp_capital_initial": float(lpp_capital_initial),
        "salaire_coordonne_max": float(salaire_coordonne_max),
        "couvrir_surobligatoire": couvrir_surobligatoire,
        "taux_cotisation_employe_lpp_paliers": taux_cotisation_employe_lpp_paliers,
        "taux_cotisation_employeur_lpp_paliers": taux_cotisation_employeur_lpp_paliers,
        "montant_mensuel_3a": float(montant_mensuel_3a),
        "rendement_3a": float(rendement_3a),
        "montant_mensuel_sp500": float(montant_mensuel_sp500),
        "rendement_sp500": float(rendement_sp500),
        "taux_dividendes_sp500": float(taux_dividendes_sp500),
        "taux_imposition_dividendes": float(taux_imposition_dividendes),
    }


def collecter_parametres() -> Tuple[Dict[str, float], bool, Optional[Dict[str, float]]]:
    """Collecte les paramètres pour l'utilisateur et, si souhaité, pour un partenaire."""

    defaults_main = {
        "age_depart": 40,
        "age_retraite": 65,
        "inflation": 2.0,
        "salaire": 78_000,
        "evol_salaire": 2.0,
        "rendement_lpp": 2.5,
        "coordination": 25_725,
        "capital_lpp": 2_000,
        "plafond": 88_200,
        "suroblig": False,
        "montant_3a": 250,
        "rendement_3a": 2.0,
        "montant_sp500": 250,
        "rendement_sp500": 8.0,
        "dividendes_sp500": 2.0,
        "taux_imposition_dividendes": 25.0,
        "taux_emp_paliers": {
            "moins_30": 7.0,
            "30_39": 10.0,
            "40_49": 15.0,
            "50_plus": 18.0,
        },
        "taux_empres_paliers": {
            "moins_30": 8.0,
            "30_39": 11.0,
            "40_49": 16.0,
            "50_plus": 19.0,
        },
    }

    defaults_partner = {
        **defaults_main,
        "age_depart": 38,
        "age_retraite": 64,
    }
    defaults_partner["taux_emp_paliers"] = defaults_main["taux_emp_paliers"].copy()
    defaults_partner["taux_empres_paliers"] = defaults_main["taux_empres_paliers"].copy()

    params_principal = saisir_parametres_personne("principal", "Profil principal", defaults_main)

    couple_mode = st.checkbox(
        "Ajouter un partenaire / une partenaire",
        value=False,
        help="Activez pour saisir un deuxième profil et agréger les résultats du couple.",
        key="couple_mode",
    )

    params_partenaire: Optional[Dict[str, float]] = None
    if couple_mode:
        params_partenaire = saisir_parametres_personne("partenaire", "Profil partenaire", defaults_partner)

    return params_principal, couple_mode, params_partenaire


def formater_delta(valeur: float) -> str:
    """Formatte un delta monétaire pour affichage dans les métriques Streamlit."""

    if abs(valeur) < 1e-6:
        return formater_chf(0.0)
    signe = "+" if valeur > 0 else ""
    return f"{signe}{formater_chf(valeur)}"


def afficher_resultats(
    resultat,
    titre: str,
    key_prefix: str,
    comparaison: Optional["ResultatPrevoyance"] = None,
) -> None:
    """Affiche les indicateurs pour un profil donné."""

    st.subheader(titre)

    delta_nominal = (
        resultat.capital_total_nominal - comparaison.capital_total_nominal
        if comparaison is not None
        else None
    )
    delta_reel = (
        resultat.capital_total_reel - comparaison.capital_total_reel
        if comparaison is not None
        else None
    )
    delta_3a = (
        resultat.capital_3a_nominal - comparaison.capital_3a_nominal
        if comparaison is not None
        else None
    )
    delta_sp500 = (
        resultat.capital_sp500_nominal - comparaison.capital_sp500_nominal
        if comparaison is not None
        else None
    )
    delta_lpp = (
        resultat.capital_lpp_nominal - comparaison.capital_lpp_nominal
        if comparaison is not None
        else None
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Capital total nominal",
        formater_chf(resultat.capital_total_nominal),
        delta=formater_delta(delta_nominal) if delta_nominal is not None else None,
        help=f"Pouvoir d'achat réel : {formater_chf(resultat.capital_total_reel)}",
    )
    col2.metric(
        "Capital total réel",
        formater_chf(resultat.capital_total_reel),
        delta=formater_delta(delta_reel) if delta_reel is not None else None,
        help="Valorisation en pouvoir d'achat constant (inflation moyenne).",
    )
    col3.metric(
        "Capital 3ᵉ pilier (nominal)",
        formater_chf(resultat.capital_3a_nominal),
        delta=formater_delta(delta_3a) if delta_3a is not None else None,
        help=f"Pouvoir d'achat réel : {formater_chf(resultat.capital_3a_reel)}",
    )
    col4.metric(
        "Capital S&P 500 (nominal)",
        formater_chf(resultat.capital_sp500_nominal),
        delta=formater_delta(delta_sp500) if delta_sp500 is not None else None,
        help=f"Pouvoir d'achat réel : {formater_chf(resultat.capital_sp500_reel)}",
    )

    st.markdown("---")
    st.markdown("#### Détail par pilier")

    col_a, col_b, col_c = st.columns(3)
    col_a.write("##### 3ᵉ pilier A")
    col_a.write(f"Versements totaux : {formater_chf(resultat.versements_totaux_3a)}")
    gain_3a = resultat.capital_3a_nominal - resultat.versements_totaux_3a
    col_a.write(f"Intérêts cumulés : {formater_chf(gain_3a)}")

    col_b.write("##### S&P 500")
    col_b.write(f"Versements totaux : {formater_chf(resultat.versements_totaux_sp500)}")
    plus_values = resultat.capital_sp500_nominal - resultat.versements_totaux_sp500
    col_b.write(f"Plus-values nettes : {formater_chf(plus_values)}")

    col_c.write("##### LPP (2ᵉ pilier)")
    col_c.write(f"Cotisations totales : {formater_chf(resultat.cotisations_totales_lpp)}")
    col_c.write(
        f"Part employé : {formater_chf(resultat.cotisations_employe_lpp)}\n"
        f"Part employeur : {formater_chf(resultat.cotisations_employeur_lpp)}"
    )

    if resultat.montant_retrait_immo > 0 and resultat.annee_retrait is not None:
        st.info(
            f"Retrait immobilier année {resultat.annee_retrait} : "
            f"{formater_chf(resultat.montant_retrait_immo)} (LPP + 3ᵉ pilier + S&P 500)."
        )

    st.markdown("---")
    st.markdown("#### Rente LPP estimée")

    taux_conversion = 0.055
    rente_lpp_annuelle = resultat.capital_lpp_nominal * taux_conversion
    rente_lpp_mensuelle = rente_lpp_annuelle / 12
    delta_rente = (
        rente_lpp_annuelle
        - (comparaison.capital_lpp_nominal * taux_conversion)
        if comparaison is not None
        else None
    )
    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric("Taux de conversion", f"{taux_conversion*100:.1f} %")
    col_r2.metric(
        "Rente annuelle (nominale)",
        formater_chf(rente_lpp_annuelle),
        delta=formater_delta(delta_rente) if delta_rente is not None else None,
    )
    col_r3.metric("Rente mensuelle (nominale)", formater_chf(rente_lpp_mensuelle))
    st.caption(
        "Hypothèse : taux de conversion 5,5 % (moyenne ASIP 2024). Ajustez selon votre caisse."
    )

    st.markdown("---")
    st.markdown("#### Évolution annuelle")

    df = pd.DataFrame(resultat.detail_annuel)
    colonnes_affichees = [
        "annee",
        "age",
        "salaire_brut",
        "salaire_coordonne",
        "cotisation_totale",
        "capital_lpp",
        "capital_3a",
        "capital_sp500",
        "capital_total",
    ]
    if "retrait_immo_total" in df.columns:
        colonnes_affichees.append("retrait_immo_total")
    df_affichage = df[colonnes_affichees].copy()
    st.dataframe(
        df_affichage.style.format(
            {
                col: "{:,.0f}".format
                for col in df_affichage.columns
                if col not in {"annee", "age"}
            }
        ),
        hide_index=True,
        width="stretch",
        key=f"{key_prefix}_table_detail",
    )

    st.download_button(
        "Télécharger le détail annuel (CSV)",
        data=df_affichage.to_csv(index=False).encode("utf-8"),
        file_name=f"projection_{key_prefix}.csv",
        mime="text/csv",
        key=f"{key_prefix}_download",
    )


def afficher_synthese_couple(
    resultat_a,
    resultat_b,
    titre: str,
    key_prefix: str,
    comparaison: Optional[Tuple["ResultatPrevoyance", "ResultatPrevoyance"]] = None,
) -> None:
    """Affiche une synthèse agrégée pour le couple."""

    st.subheader(titre)

    capital_total_nominal = resultat_a.capital_total_nominal + resultat_b.capital_total_nominal
    capital_total_reel = resultat_a.capital_total_reel + resultat_b.capital_total_reel
    delta_couple = None
    delta_couple_reel = None
    if comparaison is not None:
        ref_a, ref_b = comparaison
        delta_couple = capital_total_nominal - (
            ref_a.capital_total_nominal + ref_b.capital_total_nominal
        )
        delta_couple_reel = capital_total_reel - (
            ref_a.capital_total_reel + ref_b.capital_total_reel
        )

    retrait_total = resultat_a.montant_retrait_immo + resultat_b.montant_retrait_immo
    annee_retrait = resultat_a.annee_retrait

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Capital cumulé nominal",
        formater_chf(capital_total_nominal),
        delta=formater_delta(delta_couple) if delta_couple is not None else None,
    )
    col2.metric(
        "Capital cumulé réel",
        formater_chf(capital_total_reel),
        delta=formater_delta(delta_couple_reel) if delta_couple_reel is not None else None,
    )
    col3.metric(
        "Retrait immobilier cumulé",
        formater_chf(retrait_total),
        help="Somme des retraits LPP, 3ᵉ pilier et S&P 500 pour l'investissement immobilier.",
    )
    if retrait_total > 0 and annee_retrait is not None:
        st.info(
            f"Montant total investi dans l'immobilier en année {annee_retrait} : "
            f"{formater_chf(retrait_total)}."
        )

    df_a = pd.DataFrame(resultat_a.detail_annuel)[["annee", "capital_total"]]
    df_b = pd.DataFrame(resultat_b.detail_annuel)[["annee", "capital_total"]]
    df_a = df_a.rename(columns={"capital_total": "capital_total_principal"})
    df_b = df_b.rename(columns={"capital_total": "capital_total_partenaire"})
    df_couple = pd.merge(df_a, df_b, on="annee", how="outer").fillna(0)
    df_couple["capital_total_couple"] = (
        df_couple["capital_total_principal"] + df_couple["capital_total_partenaire"]
    )

    st.dataframe(
        df_couple.style.format(
            {
                "capital_total_principal": "{:,.0f}".format,
                "capital_total_partenaire": "{:,.0f}".format,
                "capital_total_couple": "{:,.0f}".format,
            }
        ),
        hide_index=True,
        width="stretch",
        key=f"{key_prefix}_table_couple",
    )
    st.download_button(
        "Télécharger le détail couple (CSV)",
        data=df_couple.to_csv(index=False).encode("utf-8"),
        file_name=f"projection_{key_prefix}.csv",
        mime="text/csv",
        key=f"{key_prefix}_download",
    )


def main() -> None:
    st.title("Projection de prévoyance retraite suisse")
    st.write(
        """
        Cette application fonctionne **uniquement en local** et vous aide à
        simuler vos capitaux à la retraite en combinant le 2ᵉ pilier (LPP), le
        3ᵉ pilier A et un investissement indiciel de type S&P 500.
        """
    )

    afficher_contextualisation()
    params_principal, couple_mode, params_partenaire = collecter_parametres()

    if params_principal["age_retraite"] <= params_principal["age_depart"]:
        st.error("L'âge de retraite doit être strictement supérieur à l'âge actuel.")
        return

    calculateur_principal = CalculateurPrevoyance(**params_principal)
    resultat_principal = calculateur_principal.calculer()

    calculateur_partenaire: Optional[CalculateurPrevoyance] = None
    resultat_partenaire = None
    if couple_mode and params_partenaire is not None:
        if params_partenaire["age_retraite"] <= params_partenaire["age_depart"]:
            st.error("Pour le partenaire, l'âge de retraite doit dépasser l'âge actuel.")
            return
        calculateur_partenaire = CalculateurPrevoyance(**params_partenaire)
        resultat_partenaire = calculateur_partenaire.calculer()

    st.divider()
    st.header("Résultats à la retraite")

    if couple_mode and resultat_partenaire is not None:
        onglets = st.tabs(["Profil principal", "Partenaire", "Couple"])
        with onglets[0]:
            afficher_resultats(resultat_principal, "Profil principal", "principal_base")
        with onglets[1]:
            afficher_resultats(resultat_partenaire, "Profil partenaire", "partenaire_base")
        with onglets[2]:
            afficher_synthese_couple(
                resultat_principal,
                resultat_partenaire,
                "Synthèse couple",
                key_prefix="couple_base",
            )
    else:
        afficher_resultats(resultat_principal, "Profil principal", "principal_base")

    st.divider()
    st.header("Scénario : investissement immobilier (retrait total LPP + piliers 3a & S&P 500)")
    scenario_immo = st.checkbox(
        "Activer le scénario immobilier",
        value=False,
        help="Simule un retrait unique des capitaux LPP, 3ᵉ pilier et S&P 500 à une année n pour financer un bien immobilier.",
        key="scenario_immo_checkbox",
    )

    if scenario_immo:
        max_annees = calculateur_principal.annees
        if couple_mode and calculateur_partenaire is not None:
            max_annees = min(max_annees, calculateur_partenaire.annees)

        if max_annees <= 0:
            st.warning("Impossible de simuler ce scénario : aucune année restante avant la retraite.")
        else:
            valeur_defaut = min(10, max_annees)
            annee_retrait = st.slider(
                "Choisir l'année du retrait immobilier (nombre d'années à partir d'aujourd'hui)",
                min_value=1,
                max_value=max_annees,
                value=valeur_defaut,
                help="Exemple : 10 signifie retrait dans 10 ans. Le capital est remis à zéro après le retrait, mais les cotisations continuent jusqu'à la retraite.",
                key="scenario_immo_annee",
            )

            resultat_principal_immo = calculateur_principal.calculer(annee_retrait=annee_retrait)

            if couple_mode and calculateur_partenaire is not None and resultat_partenaire is not None:
                resultat_partenaire_immo = calculateur_partenaire.calculer(annee_retrait=annee_retrait)
                onglets_immo = st.tabs(
                    [
                        "Profil principal (immo)",
                        "Partenaire (immo)",
                        "Couple (immo)",
                    ]
                )
                with onglets_immo[0]:
                    afficher_resultats(
                        resultat_principal_immo,
                        f"Profil principal – retrait année {annee_retrait}",
                        "principal_immo",
                        comparaison=resultat_principal,
                    )
                with onglets_immo[1]:
                    afficher_resultats(
                        resultat_partenaire_immo,
                        f"Profil partenaire – retrait année {annee_retrait}",
                        "partenaire_immo",
                        comparaison=resultat_partenaire,
                    )
                with onglets_immo[2]:
                    afficher_synthese_couple(
                        resultat_principal_immo,
                        resultat_partenaire_immo,
                        f"Synthèse couple – retrait année {annee_retrait}",
                        key_prefix="couple_immo",
                        comparaison=(resultat_principal, resultat_partenaire),
                    )
            else:
                afficher_resultats(
                    resultat_principal_immo,
                    f"Profil principal – retrait année {annee_retrait}",
                    "principal_immo",
                    comparaison=resultat_principal,
                )

    st.caption(
        "Sources : OFAS, ESTV, ASIP, S&P Dow Jones Indices, Morningstar, OFS, "
        "Moneyland (données 2023-2024)."
    )


if __name__ == "__main__":
    main()


