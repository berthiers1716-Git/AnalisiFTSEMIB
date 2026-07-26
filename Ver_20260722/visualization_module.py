# File: visualization_module.py
#
# [VERSIONE v2 - CON GRAFICI DEX E VEX]
# Contiene TUTTE le funzioni di plotting, incluse le nuove:
# - create_dex_profile_chart: Delta Exposure per Strike (colori bullish/bearish)
# - create_vex_profile_chart: Vanna Exposure per Strike (colori viola/arancione)
# -----------------------------------------------------------------------------

import plotly.graph_objects as go
import numpy as np
import pandas as pd
from scipy.interpolate import griddata

# -----------------------------------------------------------------------------
# 1. TEMA GRAFICO PROFESSIONALE
# -----------------------------------------------------------------------------
KRITERION_THEME = {
    'paper_bgcolor': '#0e1117',  'plot_bgcolor': '#111827',
    'font_color': '#e5e7eb',     'gridcolor': '#1f2937',
    'zerolinecolor': '#6b7280',  'color_bullish': '#10b981',
    'color_bearish': '#ef4444',  'color_neutral': '#3b82f6',
    'color_accent': '#facc15',
    # Colori esclusivi per VEX/DEX — non confondibili con il GEX
    'color_vex_pos': '#8b5cf6',  # Viola (VEX positivo)
    'color_vex_neg': '#f97316',  # Arancione (VEX negativo)
    'color_dex_pos': '#10b981',  # Verde (DEX positivo) — coerente con le caption utente
    'color_dex_neg': '#ef4444',  # Rosso  (DEX negativo) — coerente con le caption utente
    # NB: l'attribuzione "dealer long/short" della DEX e' un'IPOTESI di modello (delta grezzo
    # per OI, nessuna convenzione di segno dealer applicata), non una posizione osservata.
}


def apply_kriterion_theme(fig):
    """Applica il layout standard Kriterion Quant a una figura Plotly."""
    fig.update_layout(
        paper_bgcolor=KRITERION_THEME['paper_bgcolor'],
        plot_bgcolor=KRITERION_THEME['plot_bgcolor'],
        font=dict(color=KRITERION_THEME['font_color'], family='Inter, sans-serif'),
        xaxis=dict(gridcolor=KRITERION_THEME['gridcolor'], zerolinecolor=KRITERION_THEME['zerolinecolor']),
        yaxis=dict(gridcolor=KRITERION_THEME['gridcolor']),
        hovermode="y unified",
        hoverlabel=dict(bgcolor="#1f2937", font_size=12, font_family="Monaco, monospace"),
        annotations=[
            dict(
                text="Kriterion Quant", textangle=0, opacity=0.1,
                font=dict(color=KRITERION_THEME['font_color'], size=40),
                xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False
            )
        ]
    )
    return fig


# -----------------------------------------------------------------------------
# 2. GEX PROFILE (Orizzontale)
# -----------------------------------------------------------------------------
def create_gex_profile_chart(df_gex_profile, spot_price, gamma_switch_point, expiry_label):
    """Crea il Bar Chart GEX (orizzontale, strike su Asse Y)."""
    range_lower = spot_price * 0.80
    range_upper = spot_price * 1.20
    df_plot = df_gex_profile[
        (df_gex_profile['Strike'] >= range_lower) &
        (df_gex_profile['Strike'] <= range_upper)
    ].copy()

    df_plot['Color'] = np.where(
        df_plot['Net_GEX'] > 0,
        KRITERION_THEME['color_bullish'],
        KRITERION_THEME['color_bearish']
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_plot['Net_GEX'], y=df_plot['Strike'],
        orientation='h', marker_color=df_plot['Color'], name="Net GEX",
        hovertemplate="<b>Strike: %{y}</b><br>Net GEX: %{x:,.0f}<extra></extra>"
    ))
    fig.add_hline(
        y=spot_price, line_width=2, line_dash="dot",
        line_color=KRITERION_THEME['color_neutral'],
        annotation_text=f"Spot: {spot_price:.2f}", annotation_position="bottom right"
    )
    if gamma_switch_point is not None:
        fig.add_hline(
            y=gamma_switch_point, line_width=2, line_dash="dash",
            line_color=KRITERION_THEME['color_accent'],
            annotation_text=f"Gamma Flip: {gamma_switch_point:.2f}", annotation_position="bottom left"
        )

    fig = apply_kriterion_theme(fig)
    fig.update_layout(
        title=f"Profilo GEX (Scadenza: {expiry_label})",
        xaxis_title="Net GEX (Notional $) — vista ±20% spot; il Net totale include tutti gli strike",
        yaxis_title="Strike Price",
        height=1200, yaxis=dict(autorange="reversed")
    )
    return fig


# -----------------------------------------------------------------------------
# 3. OI DISTRIBUTION (Orizzontale)
# -----------------------------------------------------------------------------
def create_oi_profile_chart(df_oi_profile, spot_price, expiry_label):
    """Crea il Grafico OI Bidirezionale (orizzontale, strike su Asse Y)."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_oi_profile['Calls_OI'], y=df_oi_profile['Strike'],
        orientation='h', name="Calls OI (Resistenza)", marker_color=KRITERION_THEME['color_bullish'],
        hovertemplate="<b>Strike: %{y}</b><br>Calls OI: %{x:,.0f}<extra></extra>"
    ))
    fig.add_trace(go.Bar(
        x=df_oi_profile['Puts_OI_Neg'], y=df_oi_profile['Strike'],
        orientation='h', name="Puts OI (Supporto)", marker_color=KRITERION_THEME['color_bearish'],
        customdata=df_oi_profile['Puts_OI'],
        hovertemplate="<b>Strike: %{y}</b><br>Puts OI: %{customdata:,.0f}<extra></extra>"
    ))
    fig.add_hline(
        y=spot_price, line_width=2, line_dash="dot",
        line_color=KRITERION_THEME['color_neutral'],
        annotation_text=f"Spot: {spot_price:.2f}", annotation_position="bottom right"
    )
    fig = apply_kriterion_theme(fig)
    fig.update_layout(
        title=f"Distribuzione OI (Scadenza: {expiry_label})",
        xaxis_title="Open Interest (Puts: Negativo, Calls: Positivo)", yaxis_title="Strike Price",
        barmode='relative', height=1200, yaxis=dict(autorange="reversed")
    )
    return fig


# -----------------------------------------------------------------------------
# 4. VOLUME DISTRIBUTION (Orizzontale)
# -----------------------------------------------------------------------------
def create_volume_profile_chart(df_vol_profile, spot_price, expiry_label):
    """Crea il Grafico Volumi Bidirezionale (orizzontale, strike su Asse Y)."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_vol_profile['Calls_Vol'], y=df_vol_profile['Strike'],
        orientation='h', name="Calls Volume", marker_color=KRITERION_THEME['color_bullish'],
        hovertemplate="<b>Strike: %{y}</b><br>Calls Vol: %{x:,.0f}<extra></extra>"
    ))
    fig.add_trace(go.Bar(
        x=df_vol_profile['Puts_Vol_Neg'], y=df_vol_profile['Strike'],
        orientation='h', name="Puts Volume", marker_color=KRITERION_THEME['color_bearish'],
        customdata=df_vol_profile['Puts_Vol'],
        hovertemplate="<b>Strike: %{y}</b><br>Puts Vol: %{customdata:,.0f}<extra></extra>"
    ))
    fig.add_hline(
        y=spot_price, line_width=2, line_dash="dot",
        line_color=KRITERION_THEME['color_neutral'],
        annotation_text=f"Spot: {spot_price:.2f}", annotation_position="bottom right"
    )
    fig = apply_kriterion_theme(fig)
    fig.update_layout(
        title=f"Distribuzione Volumi (Scadenza: {expiry_label})",
        xaxis_title="Volume (Puts: Negativo, Calls: Positivo)", yaxis_title="Strike Price",
        barmode='relative', height=1200, yaxis=dict(autorange="reversed")
    )
    return fig


# -----------------------------------------------------------------------------
# 5. MAX PAIN (Orizzontale)
# -----------------------------------------------------------------------------
def create_max_pain_chart(df_payouts, max_pain_strike, expiry_label):
    """Crea il grafico del Payout Totale (Max Pain)."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_payouts['Total_Payout'], y=df_payouts['Strike'],
        orientation='h', name="Total Payout ($)", marker_color=KRITERION_THEME['color_neutral'],
        hovertemplate="<b>Strike: %{y}</b><br>Total Payout: %{x:,.0f}<extra></extra>"
    ))
    fig.add_hline(
        y=max_pain_strike, line_width=2, line_dash="dash",
        line_color=KRITERION_THEME['color_accent'],
        annotation_text=f"Max Pain: {max_pain_strike:.0f}", annotation_position="bottom left"
    )
    fig = apply_kriterion_theme(fig)
    fig.update_layout(
        title=f"Payout Totale a Scadenza (Max Pain) per {expiry_label}",
        xaxis_title="Payout Totale ($)", yaxis_title="Strike Price",
        height=1200, yaxis=dict(autorange="reversed")
    )
    return fig


# -----------------------------------------------------------------------------
# 6. VOLATILITY SURFACE 3D
# -----------------------------------------------------------------------------
def create_volatility_surface_3d(df_all_processed, min_delta=0.05):
    """
    Crea la superficie 3D della Volatilità Implicita (IV).

    min_delta: soglia sul |Delta|. Tiene solo le opzioni con |Delta| >= min_delta,
    escludendo le ali profondamente OTM (delta ~0) che sono illiquide, di fatto
    intradabili e con IV quotata inaffidabile (picchi artificiali fino al 200-300%).
    Il delta e' una misura di "quanto OTM" migliore della sola distanza in strike,
    perche' tiene conto di tempo alla scadenza e volatilita'.
    """
    try:
        df_surf_puts  = df_all_processed[(df_all_processed['Type'] == 'Put') &
                                         (df_all_processed['Moneyness'] < 1.0) &
                                         (df_all_processed['Delta'].abs() >= min_delta)].copy()
        df_surf_calls = df_all_processed[(df_all_processed['Type'] == 'Call') &
                                         (df_all_processed['Moneyness'] > 1.0) &
                                         (df_all_processed['Delta'].abs() >= min_delta)].copy()
        df_surf = pd.concat([df_surf_puts, df_surf_calls])
        # IV = volatilita' implicita annualizzata, frazione decimale (0.14 = 14%).
        # Cap di sicurezza a 2.0 (200%) contro eventuali outlier residui.
        df_surf = df_surf[(df_surf['IV'] > 0.01) & (df_surf['IV'] < 2.00)]
        df_surf = df_surf.dropna(subset=['IV', 'DTE_Days', 'Strike', 'Delta'])
        if len(df_surf) < 20:
            raise Exception("Dati OTM insufficienti.")

        x_grid = np.linspace(df_surf['DTE_Days'].min(), df_surf['DTE_Days'].max(), 50)
        y_grid = np.linspace(df_surf['Strike'].min(), df_surf['Strike'].max(), 50)
        X_grid, Y_grid = np.meshgrid(x_grid, y_grid)
        pts    = (df_surf['DTE_Days'], df_surf['Strike'])
        Z_lin  = griddata(pts, df_surf['IV'], (X_grid, Y_grid), method='linear')
        # Riempi i buchi (NaN fuori dall'inviluppo convesso) con 'nearest': niente fori fuorvianti.
        Z_near = griddata(pts, df_surf['IV'], (X_grid, Y_grid), method='nearest')
        Z_grid = np.where(np.isnan(Z_lin), Z_near, Z_lin)
        # IV in PERCENTUALE per leggibilita' (0.14 -> 14%): l'asse mostra 20, 40, 60... non 0.2, 0.4.
        Z_grid_pct = Z_grid * 100.0

        fig = go.Figure()
        fig.add_trace(go.Surface(
            x=X_grid, y=Y_grid, z=Z_grid_pct,
            colorscale='Viridis', colorbar_title='IV (%)',
            name="IV Surface",
            hovertemplate="<b>DTE: %{x:.0f} gg</b><br>Strike: %{y:.0f}<br>IV: %{z:.1f}%<extra></extra>"
        ))
        fig = apply_kriterion_theme(fig)
        fig.update_layout(
            title="Superficie di Volatilità Implicita (IV) - OTM (Tutte le Scadenze)",
            scene=dict(
                xaxis_title='Days to Expiry (DTE)', yaxis_title='Strike Price', zaxis_title='Implied Volatility (%)',
                xaxis=dict(gridcolor=KRITERION_THEME['gridcolor']),
                yaxis=dict(gridcolor=KRITERION_THEME['gridcolor']),
                zaxis=dict(gridcolor=KRITERION_THEME['gridcolor']),
                bgcolor=KRITERION_THEME['paper_bgcolor']
            ),
            scene_camera_eye=dict(x=1.8, y=-1.8, z=0.8), height=900
        )
        return fig
    except Exception as e:
        print(f"[ERRORE in create_volatility_surface_3d]: {e}")
        fig = go.Figure()
        fig = apply_kriterion_theme(fig)
        fig.add_annotation(
            text="Dati OTM insufficienti per costruire la superficie di volatilità.",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color=KRITERION_THEME['font_color'])
        )
        fig.update_layout(title="Superficie di Volatilità Implicita (IV)", height=900)
        return fig


# -----------------------------------------------------------------------------
# 7. ACTIVITY RATIO / DRIFT DETAIL (Orizzontale)
# -----------------------------------------------------------------------------
def create_activity_ratio_chart(df_activity_profile, spot_price, expiry_label):
    """Crea il Grafico del Rapporto Vol/OI (Drift) (orizzontale)."""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_activity_profile['Call_Activity_Ratio'],
        y=df_activity_profile['Strike'],
        orientation='h', name="Call Activity (Vol/OI)", marker_color=KRITERION_THEME['color_bullish'],
        customdata=df_activity_profile['Call_Vol'],
        hovertemplate="<b>Strike: %{y}</b><br>Rapporto Attività: %{x:.2f}<br>Volume: %{customdata:,.0f}<extra></extra>"
    ))
    fig.add_trace(go.Bar(
        x=df_activity_profile['Put_Activity_Ratio_Neg'],
        y=df_activity_profile['Strike'],
        orientation='h', name="Put Activity (Vol/OI)", marker_color=KRITERION_THEME['color_bearish'],
        customdata=df_activity_profile['Put_Activity_Ratio'],
        hovertemplate="<b>Strike: %{y}</b><br>Rapporto Attività: %{customdata:.2f}<extra></extra>"
    ))
    fig.add_hline(
        y=spot_price, line_width=2, line_dash="dot",
        line_color=KRITERION_THEME['color_neutral'],
        annotation_text=f"Spot: {spot_price:.2f}", annotation_position="bottom right"
    )
    fig = apply_kriterion_theme(fig)
    fig.update_layout(
        title=f"Analisi Drift (Rapporto Vol/OI) per {expiry_label}",
        xaxis_title="Rapporto Attività (Volume / (OI+1))",
        yaxis_title="Strike Price", barmode='relative', height=800,
        yaxis=dict(autorange="reversed")
    )
    return fig


# -----------------------------------------------------------------------------
# 8. DRIFT ARROW (Sintesi)
# -----------------------------------------------------------------------------
def create_drift_arrow_chart(drift_score, spot_price, expiry_label):
    """Crea un grafico a freccia che sintetizza la direzione del drift dei volumi."""
    fig = go.Figure()

    if drift_score > spot_price:
        color = KRITERION_THEME['color_bullish']
        text  = f"Drift Rialzista: {drift_score:.2f}"
    elif drift_score < spot_price:
        color = KRITERION_THEME['color_bearish']
        text  = f"Drift Ribassista: {drift_score:.2f}"
    else:
        color = KRITERION_THEME['color_neutral']
        text  = f"Drift Neutrale: {drift_score:.2f}"

    min_val = min(spot_price, drift_score)
    max_val = max(spot_price, drift_score)
    padding = (max_val - min_val) * 1.5
    if padding == 0:
        padding = spot_price * 0.01
    x_range = [min_val - padding, max_val + padding]

    fig.add_trace(go.Scatter(
        x=[spot_price, drift_score], y=[0, 0],
        mode='lines+markers',
        marker=dict(
            symbol='arrow-right' if drift_score >= spot_price else 'arrow-left',
            size=15, color=color, angleref="previous"
        ),
        line=dict(width=4, color=color),
        name="Drift Direzionale",
        hovertemplate=f"Drift Score: {drift_score:.2f}<extra></extra>"
    ))
    fig.add_vline(
        x=spot_price, line_width=2, line_dash="dot",
        line_color=KRITERION_THEME['color_neutral'],
        annotation_text=f"Spot: {spot_price:.2f}", annotation_position="top"
    )
    fig = apply_kriterion_theme(fig)
    fig.update_layout(
        title=f"Sintesi Drift Volumi (VWAS) vs Spot ({expiry_label})",
        xaxis_title="Strike Price",
        yaxis_visible=False, showlegend=False, height=200,
        xaxis=dict(range=x_range)
    )
    return fig


# -----------------------------------------------------------------------------
# 9. DEX PROFILE (Orizzontale) — NUOVO
# -----------------------------------------------------------------------------
def create_dex_profile_chart(df_dex_profile, spot_price, expiry_label):
    """
    Crea il Bar Chart della Delta Exposure (DEX) per Strike.

    Stile: Bar chart orizzontale (strike su asse Y), identico al GEX.
    Colori: Verde (DEX netto positivo), Rosso (DEX netto negativo).

    Interpretazione (esposizione aggregata dell'open interest, NON dei dealer):
    - DEX > 0: a quello strike l'OI e' net-long delta (prevale il delta delle call).
    - DEX < 0: a quello strike l'OI e' net-short delta (prevale il delta delle put).

    Args:
        df_dex_profile : DataFrame con colonne ['Strike', 'Net_DEX']
        spot_price     : Prezzo corrente del sottostante
        expiry_label   : Label della scadenza per il titolo del grafico
    """
    range_lower = spot_price * 0.80
    range_upper = spot_price * 1.20
    df_plot = df_dex_profile[
        (df_dex_profile['Strike'] >= range_lower) &
        (df_dex_profile['Strike'] <= range_upper)
    ].copy()

    df_plot['Color'] = np.where(
        df_plot['Net_DEX'] > 0,
        KRITERION_THEME['color_dex_pos'],
        KRITERION_THEME['color_dex_neg']
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_plot['Net_DEX'],
        y=df_plot['Strike'],
        orientation='h',
        marker_color=df_plot['Color'],
        name="Net DEX",
        hovertemplate=(
            "<b>Strike: %{y}</b><br>"
            "Net DEX: $%{x:,.0f}<extra></extra>"
        )
    ))

    # Linea Spot
    fig.add_hline(
        y=spot_price, line_width=2, line_dash="dot",
        line_color=KRITERION_THEME['color_neutral'],
        annotation_text=f"Spot: {spot_price:.2f}",
        annotation_position="bottom right"
    )

    fig = apply_kriterion_theme(fig)
    fig.update_layout(
        title=f"Profilo Delta Exposure — DEX (Scadenza: {expiry_label})",
        xaxis_title="Net DEX Nozionale ($) — [Delta × OI × 100 × Spot] — vista ±20% spot",
        yaxis_title="Strike Price",
        height=1200,
        yaxis=dict(autorange="reversed")
    )
    return fig


# -----------------------------------------------------------------------------
# 10. VEX PROFILE (Orizzontale) — NUOVO
# -----------------------------------------------------------------------------
def create_vex_profile_chart(df_vex_profile, spot_price, vex_switch_point, expiry_label):
    """
    Crea il Bar Chart della Vanna Exposure (VEX) per Strike.

    Stile: Bar chart orizzontale (strike su asse Y).
    Colori: Viola (VEX netto positivo), Arancione (VEX netto negativo).
    Questi colori sono deliberatamente diversi dal GEX (verde/rosso) per
    distinguere visivamente le due analisi.

    Interpretazione (esposizione vanna aggregata dell'open interest, NON dei dealer):
    - VEX > 0 a un certo strike: il delta aggregato dell'OI aumenta se la vol sale
      (diminuisce se la vol scende) in quel nodo.
    - VEX < 0 a un certo strike: il delta aggregato dell'OI diminuisce se la vol sale.
    - Il "Vanna Flip" è il livello di prezzo (zero-vanna, ricalcolato al
      variare dello spot) dove l'esposizione vanna netta cambia segno.

    Args:
        df_vex_profile    : DataFrame con colonne ['Strike', 'Net_VEX']
        spot_price        : Prezzo corrente del sottostante
        vex_switch_point  : Strike dello zero crossing VEX (o None)
        expiry_label      : Label della scadenza per il titolo del grafico
    """
    range_lower = spot_price * 0.80
    range_upper = spot_price * 1.20
    df_plot = df_vex_profile[
        (df_vex_profile['Strike'] >= range_lower) &
        (df_vex_profile['Strike'] <= range_upper)
    ].copy()

    df_plot['Color'] = np.where(
        df_plot['Net_VEX'] > 0,
        KRITERION_THEME['color_vex_pos'],
        KRITERION_THEME['color_vex_neg']
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_plot['Net_VEX'],
        y=df_plot['Strike'],
        orientation='h',
        marker_color=df_plot['Color'],
        name="Net VEX",
        hovertemplate=(
            "<b>Strike: %{y}</b><br>"
            "Net VEX: $%{x:,.2f}<extra></extra>"
        )
    ))

    # Linea Spot
    fig.add_hline(
        y=spot_price, line_width=2, line_dash="dot",
        line_color=KRITERION_THEME['color_neutral'],
        annotation_text=f"Spot: {spot_price:.2f}",
        annotation_position="bottom right"
    )

    # Vanna Flip (zero-vanna ricalcolato al variare dello spot — linea gialla tratteggiata, stile Gamma Flip)
    if vex_switch_point is not None:
        fig.add_hline(
            y=vex_switch_point, line_width=2, line_dash="dash",
            line_color=KRITERION_THEME['color_accent'],
            annotation_text=f"Vanna Flip: {vex_switch_point:.2f}",
            annotation_position="bottom left"
        )

    fig = apply_kriterion_theme(fig)
    fig.update_layout(
        title=f"Profilo Vanna Exposure — VEX (Scadenza: {expiry_label})",
        xaxis_title="Net VEX Nozionale ($) — [Vanna × OI × 100 × Spot × 1%] — vista ±20% spot",
        yaxis_title="Strike Price",
        height=1200,
        yaxis=dict(autorange="reversed")
    )
    return fig
