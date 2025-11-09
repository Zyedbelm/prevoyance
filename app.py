"""Application Streamlit locale de projection de prévoyance retraite.

L'application reprend la logique de calcul fournie par l'utilisateur et
propose une interface pédagogique indiquant les hypothèses et fourchettes
raisonnables basées sur des sources publiques (OFAS, FINMA, données marché).
"""

from __future__ import annotations

from typing import Dict

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


def collecter_parametres() -> Dict[str, float]:
    """Collecte les paramètres utilisateur avec des bornes justifiées."""

    st.header("Paramètres de simulation")

    col_age, col_retraite, col_inflation = st.columns(3)
    age_depart = col_age.number_input(
        "Âge actuel",
        min_value=18,
        max_value=64,
        value=40,
        help="Âge légal minimal LPP 18 ans."
    )
    age_retraite = col_retraite.number_input(
        "Âge de retraite",
        min_value=age_depart + 1,
        max_value=70,
        value=65,
        help="Âge cible, par défaut 65 ans (réforme AVS 21)."
    )
    inflation_annuelle = col_inflation.slider(
        "Inflation annuelle anticipée",
        min_value=0.0,
        max_value=4.0,
        value=2.0,
        step=0.1,
        help="Inflation moyenne Suisse 1993-2023 : 0,9 %. 2022-2023 : 2,3 %."
    )

    st.header("Paramètres essentiels")
    bloc_lpp, bloc_3a, bloc_sp500 = st.columns([1.4, 1, 1])

    with bloc_lpp:
        with st.container(border=True):
            st.subheader("Salaire & LPP")
            salaire_brut_initial = st.number_input(
                "Salaire brut annuel",
                min_value=30000,
                max_value=300000,
                value=78000,
                step=1000,
                help="Salaire soumis à la LPP (source : Salarium OFS).",
            )
            evolution_salaire_annuel = st.slider(
                "Évolution salariale annuelle",
                min_value=-2.0,
                max_value=5.0,
                value=2.0,
                step=0.1,
                help="Hypothèse de progression salariale réelle (OFS : +1,5 % moyen).",
            )
            rendement_lpp = st.slider(
                "Rendement annuel LPP",
                min_value=0.5,
                max_value=3.5,
                value=2.5,
                step=0.1,
                help="Taux d'intérêt minimum LPP 2024 : 1,25 %. Moyenne caisses : ~2,1 %.",
            )
            montant_coordination = st.number_input(
                "Montant de coordination",
                min_value=0,
                max_value=40000,
                value=25725,
                step=25,
                help="Déduction légale LPP 2024 : CHF 25 725 (OFAS).",
            )
            col_plafond, col_suroblig = st.columns([2, 1])
            salaire_coordonne_max = col_plafond.number_input(
                "Salaire annuel maximum assuré LPP",
                min_value=0,
                max_value=120_000,
                value=88_200,
                step=1000,
                help="Plafond légal 2024 : CHF 88 200 (OFAS).",
            )
            couvrir_surobligatoire = col_suroblig.checkbox(
                "Inclure la partie surobligatoire",
                value=False,
                help=(
                    "Lorsque cochée, le salaire coordonné n'est plus plafonné à CHF 88 200 "
                    "et la LPP couvre également le volet surobligatoire."
                ),
            )

    with bloc_3a:
        with st.container(border=True):
            st.subheader("3ᵉ pilier A")
            montant_mensuel_3a = st.slider(
                "Versement mensuel",
                min_value=0,
                max_value=600,
                value=250,
                step=10,
                help="Plafond 2024 salariés : CHF 588/mois (ESTV).",
            )
            rendement_3a = st.slider(
                "Rendement annuel",
                min_value=0.5,
                max_value=4.0,
                value=2.0,
                step=0.1,
                help="Banques suisses : 1,0 %-2,5 % (Moneyland 2024).",
            )

    with bloc_sp500:
        with st.container(border=True):
            st.subheader("Investissement S&P 500")
            montant_mensuel_sp500 = st.slider(
                "Versement mensuel",
                min_value=0,
                max_value=2000,
                value=250,
                step=50,
                help="Adapter selon votre capacité d'épargne.",
            )
            rendement_sp500 = st.slider(
                "Rendement brut annuel",
                min_value=4.0,
                max_value=12.0,
                value=8.0,
                step=0.5,
                help="Retour moyen 1926-2023 ~10 % (Morningstar).",
            )
            taux_dividendes_sp500 = st.slider(
                "Taux de dividendes",
                min_value=1.0,
                max_value=3.0,
                value=2.0,
                step=0.1,
                help="Rendement dividendes SP500 10 ans : 1,7 %-2,2 % (S&P Dow Jones).",
            )
            taux_imposition_dividendes = st.slider(
                "Taux d'imposition marginal sur dividendes",
                min_value=0.0,
                max_value=40.0,
                value=25.0,
                step=1.0,
                help="Inclure impôts fédéraux + cantonaux + commune (ESTV).",
            )

    st.subheader("Autres paramètres LPP")
    lpp_capital_initial = st.number_input(
        "Capital LPP existant",
        min_value=0,
        max_value=2_000_000,
        value=2000,
        step=1000,
    )
    evolution_salaire_annuel = evolution_salaire_annuel  # déjà fixé ci-dessus, conserve valeur pour cohérence

    st.caption(
        "Ajustez finement la structure des cotisations LPP selon les paliers d'âge."
    )
    st.markdown("**Taux de cotisation par tranche d'âge**")
    cols_emp = st.columns(4)
    st.caption(
        "Répartition indicative inspirée des plans standards : <30 ans, 30-39, 40-49, 50+."
    )

    cols_emp = st.columns(4)
    taux_cotisation_employe_lpp_paliers = {
        "moins_30": cols_emp[0].slider(
            "Employé < 30 ans",
            min_value=4.0,
            max_value=12.0,
            value=7.0,
            step=0.1,
        ),
        "30_39": cols_emp[1].slider(
            "Employé 30-39 ans",
            min_value=5.0,
            max_value=15.0,
            value=10.0,
            step=0.1,
        ),
        "40_49": cols_emp[2].slider(
            "Employé 40-49 ans",
            min_value=6.0,
            max_value=18.0,
            value=15.0,
            step=0.1,
        ),
        "50_plus": cols_emp[3].slider(
            "Employé 50+ ans",
            min_value=8.0,
            max_value=20.0,
            value=18.0,
            step=0.1,
        ),
    }

    cols_empres = st.columns(4)
    taux_cotisation_employeur_lpp_paliers = {
        "moins_30": cols_empres[0].slider(
            "Employeur < 30 ans",
            min_value=4.0,
            max_value=15.0,
            value=8.0,
            step=0.1,
        ),
        "30_39": cols_empres[1].slider(
            "Employeur 30-39 ans",
            min_value=5.0,
            max_value=18.0,
            value=11.0,
            step=0.1,
        ),
        "40_49": cols_empres[2].slider(
            "Employeur 40-49 ans",
            min_value=6.0,
            max_value=20.0,
            value=16.0,
            step=0.1,
        ),
        "50_plus": cols_empres[3].slider(
            "Employeur 50+ ans",
            min_value=8.0,
            max_value=22.0,
            value=19.0,
            step=0.1,
        ),
    }

    return {
        "age_depart": int(age_depart),
        "age_retraite": int(age_retraite),
        "salaire_brut_initial": float(salaire_brut_initial),
        "lpp_capital_initial": float(lpp_capital_initial),
        "evolution_salaire_annuel": float(evolution_salaire_annuel),
        "montant_mensuel_3a": float(montant_mensuel_3a),
        "rendement_3a": float(rendement_3a),
        "montant_mensuel_sp500": float(montant_mensuel_sp500),
        "rendement_sp500": float(rendement_sp500),
        "taux_imposition_dividendes": float(taux_imposition_dividendes),
        "rendement_lpp": float(rendement_lpp),
        "inflation_annuelle": float(inflation_annuelle),
        "montant_coordination": float(montant_coordination),
        "salaire_coordonne_max": float(salaire_coordonne_max),
        "couvrir_surobligatoire": couvrir_surobligatoire,
        "taux_dividendes_sp500": float(taux_dividendes_sp500),
        "taux_cotisation_employe_lpp_paliers": taux_cotisation_employe_lpp_paliers,
        "taux_cotisation_employeur_lpp_paliers": taux_cotisation_employeur_lpp_paliers,
    }


def afficher_resultats(resultat, params) -> None:
    """Affiche les résultats de simulation."""

    st.header("Synthèse à la retraite")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Capital total nominal", formater_chf(resultat.capital_total_nominal))
    col2.metric(
        "Capital total réel",
        formater_chf(resultat.capital_total_reel),
        help="Pouvoir d'achat actualisé après inflation cumulative",
    )
    col3.metric(
        "Capital 3ᵉ pilier",
        formater_chf(resultat.capital_3a_nominal),
        delta=f"Réel : {formater_chf(resultat.capital_3a_reel)}",
    )
    col4.metric(
        "Capital SP500",
        formater_chf(resultat.capital_sp500_nominal),
        delta=f"Réel : {formater_chf(resultat.capital_sp500_reel)}",
    )

    st.markdown("---")
    st.subheader("Détail par pilier")

    col_a, col_b, col_c = st.columns(3)
    col_a.write("### 3ᵉ pilier A")
    col_a.write(f"Versements totaux : {formater_chf(resultat.versements_totaux_3a)}")
    gain_3a = resultat.capital_3a_nominal - resultat.versements_totaux_3a
    col_a.write(f"Intérêts cumulés : {formater_chf(gain_3a)}")

    col_b.write("### SP500")
    col_b.write(f"Versements totaux : {formater_chf(resultat.versements_totaux_sp500)}")
    plus_values = resultat.capital_sp500_nominal - resultat.versements_totaux_sp500
    col_b.write(f"Plus-values nettes : {formater_chf(plus_values)}")

    col_c.write("### LPP")
    col_c.write(
        f"Cotisations totales : {formater_chf(resultat.cotisations_totales_lpp)}"
    )
    col_c.write(
        f"Part employé : {formater_chf(resultat.cotisations_employe_lpp)}\n"
        f"Part employeur : {formater_chf(resultat.cotisations_employeur_lpp)}"
    )

    st.markdown("---")
    st.subheader("Rente LPP estimée")

    taux_conversion = 0.055
    rente_lpp_annuelle = resultat.capital_lpp_nominal * taux_conversion
    rente_lpp_mensuelle = rente_lpp_annuelle / 12
    col_r1, col_r2, col_r3 = st.columns(3)
    col_r1.metric("Taux de conversion", f"{taux_conversion*100:.1f} %")
    col_r2.metric("Rente annuelle", formater_chf(rente_lpp_annuelle))
    col_r3.metric("Rente mensuelle", formater_chf(rente_lpp_mensuelle))

    st.caption(
        "Taux moyen 2024 communiqué par l'Association Suisse des Institutions "
        "de Prévoyance (ASIP). Ajustez selon votre caisse si nécessaire."
    )

    st.markdown("---")
    st.subheader("Évolution annuelle")

    df = pd.DataFrame(resultat.detail_annuel)
    df_affichage = df[[
        "annee",
        "age",
        "salaire_brut",
        "salaire_coordonne",
        "cotisation_totale",
        "capital_lpp",
        "capital_3a",
        "capital_sp500",
        "capital_total",
    ]].copy()
    st.dataframe(
        df_affichage.style.format(
            {
                "salaire_brut": "{:,.0f}".format,
                "salaire_coordonne": "{:,.0f}".format,
                "cotisation_totale": "{:,.0f}".format,
                "capital_lpp": "{:,.0f}".format,
                "capital_3a": "{:,.0f}".format,
                "capital_sp500": "{:,.0f}".format,
                "capital_total": "{:,.0f}".format,
            }
        ),
        hide_index=True,
        width="stretch",
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
    params = collecter_parametres()

    if params["age_retraite"] <= params["age_depart"]:
        st.error("L'âge de retraite doit être strictement supérieur à l'âge actuel.")
        return

    calculateur = CalculateurPrevoyance(**params)
    resultat = calculateur.calculer()

    afficher_resultats(resultat, params)

    st.markdown("---")
    st.subheader("Export")
    df_detail = pd.DataFrame(resultat.detail_annuel)
    st.download_button(
        "Télécharger le détail annuel (CSV)",
        data=df_detail.to_csv(index=False).encode("utf-8"),
        file_name="projection_prevoyance.csv",
        mime="text/csv",
    )

    st.caption(
        "Sources : OFAS, ESTV, ASIP, S&P Dow Jones Indices, Morningstar, OFS, "
        "Moneyland (données 2023-2024)."
    )


if __name__ == "__main__":
    main()


