"""
Daily Meta Ads report — Python port of hotboat-intelligence-dashboard's
scripts/daily_meta_report.js (2026-08 handoff), adapted to run inside this
service instead of being shelled out to as a Node process: this is a
pure-Python Nixpacks build running 4 replicas, so adding a Node runtime
here risked breaking the live bot's own deploy just to email a report.
Reuses this service's existing DB connection and send_email() instead.

Keep the math/formatting here in lock-step with the JS original if that
script changes — this is a straight port, not a redesign. Queries the same
views (v_meta_ads_analytics, whatsapp_by_ad_daily_v) and table
(all_appointments) the JS version does; all on the one shared Postgres
instance, so no cross-repo access is needed.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

TRANSBANK = "Campaña Venta virales - conversion transbank"
POPEYE = "Cliente Potencial Pucón - Popeye"

_WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
_MONTHS_ES_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


# ── Formatting (mirrors fmtCLP/fmtNum/fmtPct/fmtDateLong/fmtDateShort in the JS) ──

def _cl_grouped(int_part: int) -> str:
    return f"{int_part:,}".replace(",", ".")


def fmt_clp(n: Optional[float]) -> str:
    if n is None:
        return "—"
    return "$" + _cl_grouped(round(n))


def fmt_num(n: Optional[float]) -> str:
    """Chilean-style, up to 1 decimal — matches toLocaleString('es-CL', {maximumFractionDigits:1})."""
    if n is None:
        return "—"
    rounded = round(n, 1)
    int_part = int(rounded)
    frac = round(abs(rounded) - abs(int_part), 1)
    if frac == 0:
        return _cl_grouped(int_part)
    dec_digit = str(int(round(frac * 10)))
    return f"{_cl_grouped(int_part)},{dec_digit}"


def fmt_pct(n: Optional[float]) -> str:
    if n is None:
        return "—"
    return f"{n:.1f}%"


def fmt_date_long(d: date) -> str:
    weekday = _WEEKDAYS_ES[d.weekday()]
    month = _MONTHS_ES[d.month - 1]
    return f"{weekday}, {d.day} de {month}"


def fmt_date_short(d: date) -> str:
    month = _MONTHS_ES_SHORT[d.month - 1]
    return f"{d.day} {month}"


# ── Queries (mirror the JS functions of the same purpose) ────────────────────

def _campaign_serie_by_group(cur, day: date, campaign_name: str) -> Dict[str, List[dict]]:
    cur.execute(
        """
        WITH dias AS (
            SELECT generate_series(%(day)s::date - INTERVAL '6 days', %(day)s::date, INTERVAL '1 day')::date AS day
        ),
        grupos AS (SELECT unnest(ARRAY['Pucón','Multiple']) AS grupo)
        SELECT d.day, g.grupo,
            COALESCE(SUM(a."Importe gastado (CLP)"),0)::numeric spend,
            COALESCE(SUM(a."Clics en el enlace"),0)::numeric clicks
        FROM dias d
        CROSS JOIN grupos g
        LEFT JOIN v_meta_ads_analytics a
            ON a."Día" = d.day AND a."Nombre de la campaña" = %(campaign)s
            AND (
                (g.grupo = 'Pucón' AND a."Nombre del conjunto de anuncios" ILIKE '%%puc%%') OR
                (g.grupo = 'Multiple' AND a."Nombre del conjunto de anuncios" ILIKE '%%multiple%%')
            )
        GROUP BY d.day, g.grupo ORDER BY d.day, g.grupo
        """,
        {"day": day, "campaign": campaign_name},
    )
    pucon, multiple = [], []
    for row_day, grupo, spend, clicks in cur.fetchall():
        spend, clicks = float(spend), float(clicks)
        item = {"day": row_day, "spend": spend, "clicks": clicks, "cpc": (spend / clicks) if clicks > 0 else None}
        (pucon if grupo == "Pucón" else multiple).append(item)
    return {"pucon": pucon, "multiple": multiple}


def _week_compare_cpc(cur, day: date, campaign_name: str, group_pattern: Optional[str]) -> Dict[str, dict]:
    sql = """
        SELECT
            CASE WHEN "Día" > %(day)s::date - INTERVAL '7 days' THEN 'actual' ELSE 'anterior' END AS periodo,
            COALESCE(SUM("Importe gastado (CLP)"),0)::numeric spend,
            COALESCE(SUM("Clics en el enlace"),0)::numeric clicks
        FROM v_meta_ads_analytics
        WHERE "Nombre de la campaña" = %(campaign)s
          AND "Día" > %(day)s::date - INTERVAL '14 days' AND "Día" <= %(day)s::date
    """
    params = {"day": day, "campaign": campaign_name}
    if group_pattern:
        sql += ' AND "Nombre del conjunto de anuncios" ILIKE %(pattern)s'
        params["pattern"] = f"%{group_pattern}%"
    sql += " GROUP BY 1"
    cur.execute(sql, params)
    by_period = {periodo: (float(spend), float(clicks)) for periodo, spend, clicks in cur.fetchall()}

    def calc(periodo):
        spend, clicks = by_period.get(periodo, (0.0, 0.0))
        return {"spend": spend, "clicks": clicks, "cpc": (spend / clicks) if clicks > 0 else None}

    return {"actual": calc("actual"), "anterior": calc("anterior")}


def _week_compare_popeye_funnel(cur, day: date) -> Dict[str, dict]:
    cur.execute(
        """
        SELECT CASE WHEN "Día" > %(day)s::date - INTERVAL '7 days' THEN 'actual' ELSE 'anterior' END AS periodo,
            COALESCE(SUM("Importe gastado (CLP)"),0)::numeric spend
        FROM v_meta_ads_analytics
        WHERE "Nombre de la campaña" = %(campaign)s AND "Día" > %(day)s::date - INTERVAL '14 days' AND "Día" <= %(day)s::date
        GROUP BY 1
        """,
        {"day": day, "campaign": POPEYE},
    )
    spend_by_period = {periodo: float(spend) for periodo, spend in cur.fetchall()}

    cur.execute(
        """
        SELECT CASE WHEN day > %(day)s::date - INTERVAL '7 days' THEN 'actual' ELSE 'anterior' END AS periodo,
            COALESCE(SUM(conversations),0)::numeric conversaciones, COALESCE(SUM(bookings),0)::numeric reservas
        FROM whatsapp_by_ad_daily_v
        WHERE campaign_name = %(campaign)s AND day > %(day)s::date - INTERVAL '14 days' AND day <= %(day)s::date
        GROUP BY 1
        """,
        {"day": day, "campaign": POPEYE},
    )
    conv_by_period = {periodo: (float(conv), float(res)) for periodo, conv, res in cur.fetchall()}

    def calc(periodo):
        spend = spend_by_period.get(periodo, 0.0)
        conversaciones, reservas = conv_by_period.get(periodo, (0.0, 0.0))
        return {
            "spend": spend, "conversaciones": conversaciones, "reservas": reservas,
            "costoConversacion": (spend / conversaciones) if conversaciones > 0 else None,
            "pctConversion": (100 * reservas / conversaciones) if conversaciones > 0 else None,
        }

    return {"actual": calc("actual"), "anterior": calc("anterior")}


def _popeye_funnel_serie(cur, day: date) -> List[dict]:
    cur.execute(
        """
        WITH dias AS (
            SELECT generate_series(%(day)s::date - INTERVAL '6 days', %(day)s::date, INTERVAL '1 day')::date AS day
        ),
        gasto AS (
            SELECT "Día" AS day, SUM("Importe gastado (CLP)")::numeric spend
            FROM v_meta_ads_analytics WHERE "Nombre de la campaña" = %(campaign)s AND "Día" BETWEEN %(day)s::date - INTERVAL '6 days' AND %(day)s::date
            GROUP BY 1
        ),
        conv AS (
            SELECT day, SUM(conversations)::numeric conversaciones, SUM(useful_conversations)::numeric utiles, SUM(bookings)::numeric reservas
            FROM whatsapp_by_ad_daily_v WHERE campaign_name = %(campaign)s AND day BETWEEN %(day)s::date - INTERVAL '6 days' AND %(day)s::date
            GROUP BY 1
        )
        SELECT d.day, COALESCE(g.spend,0)::numeric spend, COALESCE(c.conversaciones,0)::numeric conversaciones,
            COALESCE(c.utiles,0)::numeric utiles, COALESCE(c.reservas,0)::numeric reservas
        FROM dias d
        LEFT JOIN gasto g ON g.day = d.day
        LEFT JOIN conv c ON c.day = d.day
        ORDER BY d.day
        """,
        {"day": day, "campaign": POPEYE},
    )
    out = []
    for row_day, spend, conversaciones, utiles, reservas in cur.fetchall():
        spend, conversaciones, utiles, reservas = float(spend), float(conversaciones), float(utiles), float(reservas)
        out.append({
            "day": row_day, "spend": spend, "conversaciones": conversaciones, "utiles": utiles, "reservas": reservas,
            "costoConversacion": (spend / conversaciones) if conversaciones > 0 else None,
            "pctConversion": (100 * reservas / conversaciones) if conversaciones > 0 else None,
            "costoReserva": (spend / reservas) if reservas > 0 else None,
        })
    return out


def _sum_serie(serie: List[dict], field: str) -> float:
    return sum(d.get(field) or 0 for d in serie)


def _totales_y_prom(serie: List[dict]) -> dict:
    spend, clicks = _sum_serie(serie, "spend"), _sum_serie(serie, "clicks")
    return {
        "total": {"spend": spend, "clicks": clicks},
        "prom": {"spend": spend / 7, "clicks": clicks / 7, "cpc": (spend / clicks) if clicks > 0 else None},
    }


def _pct_delta(hoy_val: Optional[float], prom_val: Optional[float]) -> Optional[float]:
    if hoy_val is None or prom_val is None or prom_val == 0:
        return None
    return ((hoy_val - prom_val) / prom_val) * 100


def _arrow(d: Optional[float]) -> str:
    if d is None:
        return ""
    if d > 15:
        return " 🔴"
    if d < -15:
        return " 🟢"
    return " ⚪"


# ── HTML building (mirrors buildRow/headerRow/renderCpcByGroupSection/renderWeekCompareTable) ──

def _build_row(label, serie, field, fmt, *, total=None, prom=None, bold=False, note=None, is_rate=False) -> str:
    cells = []
    for i, d in enumerate(serie):
        is_last = i == len(serie) - 1
        style = "font-weight:600;background:#f5f5f4;" if is_last else "color:#525252;"
        cells.append(f'<td style="text-align:right;padding:5px 3px;{style}">{fmt(d.get(field))}</td>')
    total_cell = f'<td style="text-align:right;padding:5px 8px;font-weight:600;border-left:2px solid #e5e5e5;">{"—" if is_rate else fmt(total)}</td>'
    prom_cell = f'<td style="text-align:right;padding:5px 3px 5px 8px;font-weight:600;">{fmt(prom)}</td>'
    label_style = "font-weight:600;" if bold else ""
    note_html = f' <span style="font-weight:400;color:#a3a3a3;font-size:10px;">{note}</span>' if note else ""
    return f'<tr><td style="padding:5px 0;white-space:nowrap;{label_style}">{label}{note_html}</td>{"".join(cells)}{total_cell}{prom_cell}</tr>'


def _group_subhead_row(label: str, colspan: int) -> str:
    return (
        f'<tr><td colspan="{colspan}" style="padding:10px 0 3px;font-size:10.5px;font-weight:700;'
        f'color:#0b0b0b;text-transform:uppercase;letter-spacing:.04em;border-top:1px solid #eee;">{label}</td></tr>'
    )


def _header_row(serie: List[dict]) -> str:
    cells = []
    for i, d in enumerate(serie):
        is_last = i == len(serie) - 1
        style = "color:#0b0b0b;font-weight:700;" if is_last else ""
        suffix = "<br>(ayer)" if is_last else ""
        cells.append(f'<td style="text-align:right;padding:4px 3px;{style}">{fmt_date_short(d["day"])}{suffix}</td>')
    return (
        '<tr style="color:#a3a3a3;font-size:9.5px;text-transform:uppercase;">'
        f'<td style="padding:4px 0;"></td>{"".join(cells)}'
        '<td style="text-align:right;padding:4px 8px;border-left:2px solid #e5e5e5;">Total</td>'
        '<td style="text-align:right;padding:4px 3px 4px 8px;">Prom.<br>ponderado</td></tr>'
    )


def _render_cpc_by_group_section(by_group: Dict[str, List[dict]]) -> dict:
    pucon_stats = _totales_y_prom(by_group["pucon"])
    multiple_stats = _totales_y_prom(by_group["multiple"])
    colspan = len(by_group["pucon"]) + 3

    table = (
        '<table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:10px;">'
        f'{_header_row(by_group["pucon"])}'
        f'{_group_subhead_row("Pucón", colspan)}'
        f'{_build_row("Gasto", by_group["pucon"], "spend", fmt_clp, total=pucon_stats["total"]["spend"], prom=pucon_stats["prom"]["spend"])}'
        f'{_build_row("Clics", by_group["pucon"], "clicks", fmt_num, total=pucon_stats["total"]["clicks"], prom=pucon_stats["prom"]["clicks"])}'
        f'{_build_row("CPC", by_group["pucon"], "cpc", fmt_clp, prom=pucon_stats["prom"]["cpc"], bold=True, is_rate=True, note="(prom. ponderado)")}'
        f'{_group_subhead_row("Multiple", colspan)}'
        f'{_build_row("Gasto", by_group["multiple"], "spend", fmt_clp, total=multiple_stats["total"]["spend"], prom=multiple_stats["prom"]["spend"])}'
        f'{_build_row("Clics", by_group["multiple"], "clicks", fmt_num, total=multiple_stats["total"]["clicks"], prom=multiple_stats["prom"]["clicks"])}'
        f'{_build_row("CPC", by_group["multiple"], "cpc", fmt_clp, prom=multiple_stats["prom"]["cpc"], bold=True, is_rate=True, note="(prom. ponderado)")}'
        "</table>"
    )

    pucon_last = by_group["pucon"][-1]
    multiple_last = by_group["multiple"][-1]
    pucon_delta = _pct_delta(pucon_last["cpc"], pucon_stats["prom"]["cpc"])
    multiple_delta = _pct_delta(multiple_last["cpc"], multiple_stats["prom"]["cpc"])

    summary = (
        '<div style="font-size:12px;color:#525252;margin:0 0 20px;line-height:1.6;">'
        f'CPC Pucón ayer {fmt_clp(pucon_last["cpc"])}{_arrow(pucon_delta)} vs. prom. ponderado 7d {fmt_clp(pucon_stats["prom"]["cpc"])}<br>'
        f'CPC Multiple ayer {fmt_clp(multiple_last["cpc"])}{_arrow(multiple_delta)} vs. prom. ponderado 7d {fmt_clp(multiple_stats["prom"]["cpc"])}'
        "</div>"
    )
    return {"table": table, "summary": summary}


def _render_week_compare_table(rows: List[dict]) -> str:
    head = (
        '<tr style="color:#a3a3a3;font-size:9.5px;text-transform:uppercase;">'
        '<td style="padding:4px 0;"></td>'
        '<td style="text-align:right;padding:4px 8px;">Semana actual<br>(últ. 7 días)</td>'
        '<td style="text-align:right;padding:4px 8px;">Semana anterior<br>(días 8-14)</td>'
        '<td style="text-align:right;padding:4px 0 4px 8px;">Variación</td></tr>'
    )
    body_parts = []
    for row in rows:
        d = _pct_delta(row["actual"], row["anterior"])
        delta_txt = "—" if d is None else f'{"+" if d > 0 else ""}{d:.1f}%'
        body_parts.append(
            '<tr>'
            f'<td style="padding:6px 0;border-top:1px solid #eee;white-space:nowrap;">{row["label"]}</td>'
            f'<td style="text-align:right;padding:6px 8px;border-top:1px solid #eee;font-weight:600;">{row["fmt"](row["actual"])}</td>'
            f'<td style="text-align:right;padding:6px 8px;border-top:1px solid #eee;color:#737373;">{row["fmt"](row["anterior"])}</td>'
            f'<td style="text-align:right;padding:6px 0 6px 8px;border-top:1px solid #eee;">{delta_txt}{_arrow(d)}</td>'
            "</tr>"
        )
    return f'<table style="width:100%;border-collapse:collapse;font-size:12.5px;margin-bottom:8px;">{head}{"".join(body_parts)}</table>'


# ── Plain-text building (mirrors textGroupTable/textTable) ───────────────────

def _text_group_table(camp_name: str, by_group: Dict[str, List[dict]]) -> str:
    lines = []
    for key, label in (("pucon", "Pucón"), ("multiple", "Multiple")):
        serie = by_group[key]
        stats = _totales_y_prom(serie)
        lines.append(f"  {camp_name} · {label}")
        lines.append("  Día\t" + "\t".join([fmt_date_short(d["day"]) for d in serie] + ["Total", "Prom. ponderado"]))
        lines.append("  Gasto\t" + "\t".join([fmt_clp(d["spend"]) for d in serie] + [fmt_clp(stats["total"]["spend"]), fmt_clp(stats["prom"]["spend"])]))
        lines.append("  Clics\t" + "\t".join([fmt_num(d["clicks"]) for d in serie] + [fmt_num(stats["total"]["clicks"]), fmt_num(stats["prom"]["clicks"])]))
        lines.append("  CPC\t" + "\t".join([fmt_clp(d["cpc"]) for d in serie] + ["—", fmt_clp(stats["prom"]["cpc"])]))
        lines.append("")
    return "\n".join(lines)


def _text_table(serie: List[dict], rows: List[tuple]) -> str:
    header = "\t".join(["Día"] + [fmt_date_short(d["day"]) for d in serie] + ["Total", "Prom. ponderado"])
    lines = [header]
    for label, field, fmt, total, prom, is_rate in rows:
        vals = [fmt(d.get(field)) for d in serie]
        lines.append("\t".join([label] + vals + ["—" if is_rate else fmt(total), fmt(prom)]))
    return "\n".join(lines)


# ── Entry point ────────────────────────────────────────────────────────────

def generate_report(cur, report_date: Optional[date] = None) -> Dict[str, str]:
    """Returns {subject, html, text} for the given date (default: yesterday,
    matching the JS script's default and its "run at 9am" intent)."""
    if report_date is None:
        cur.execute("SELECT (CURRENT_DATE - INTERVAL '1 day')::date AS d")
        report_date = cur.fetchone()[0]

    tb_by_group = _campaign_serie_by_group(cur, report_date, TRANSBANK)
    pop_by_group = _campaign_serie_by_group(cur, report_date, POPEYE)
    pop_serie = _popeye_funnel_serie(cur, report_date)

    pop_total = {
        "spend": _sum_serie(pop_serie, "spend"),
        "conversaciones": _sum_serie(pop_serie, "conversaciones"),
        "reservas": _sum_serie(pop_serie, "reservas"),
    }
    pop_prom = {
        "spend": pop_total["spend"] / 7,
        "conversaciones": pop_total["conversaciones"] / 7,
        "costoConversacion": (pop_total["spend"] / pop_total["conversaciones"]) if pop_total["conversaciones"] > 0 else None,
        "pctConversion": (100 * pop_total["reservas"] / pop_total["conversaciones"]) if pop_total["conversaciones"] > 0 else None,
        "costoReserva": (pop_total["spend"] / pop_total["reservas"]) if pop_total["reservas"] > 0 else None,
    }
    popeye_delta = _pct_delta(pop_serie[-1]["costoConversacion"], pop_prom["costoConversacion"])

    cur.execute(
        """
        SELECT COUNT(*) FILTER (WHERE status NOT ILIKE '%%cancel%%')::int no_canceladas,
            COALESCE(SUM(ingreso_total) FILTER (WHERE status NOT ILIKE '%%cancel%%'),0)::numeric ingreso
        FROM all_appointments WHERE created_at::date = %s
        """,
        (report_date,),
    )
    no_canceladas, ingreso = cur.fetchone()
    ingreso = float(ingreso)

    tb_section = _render_cpc_by_group_section(tb_by_group)
    pop_cpc_section = _render_cpc_by_group_section(pop_by_group)

    tb_pucon_wk = _week_compare_cpc(cur, report_date, TRANSBANK, "puc")
    tb_multiple_wk = _week_compare_cpc(cur, report_date, TRANSBANK, "multiple")
    pop_pucon_wk = _week_compare_cpc(cur, report_date, POPEYE, "puc")
    pop_multiple_wk = _week_compare_cpc(cur, report_date, POPEYE, "multiple")
    pop_funnel_wk = _week_compare_popeye_funnel(cur, report_date)

    week_compare_rows = [
        {"label": "CPC Transbank · Pucón", "actual": tb_pucon_wk["actual"]["cpc"], "anterior": tb_pucon_wk["anterior"]["cpc"], "fmt": fmt_clp},
        {"label": "CPC Transbank · Multiple", "actual": tb_multiple_wk["actual"]["cpc"], "anterior": tb_multiple_wk["anterior"]["cpc"], "fmt": fmt_clp},
        {"label": "CPC Popeye · Pucón", "actual": pop_pucon_wk["actual"]["cpc"], "anterior": pop_pucon_wk["anterior"]["cpc"], "fmt": fmt_clp},
        {"label": "CPC Popeye · Multiple", "actual": pop_multiple_wk["actual"]["cpc"], "anterior": pop_multiple_wk["anterior"]["cpc"], "fmt": fmt_clp},
        {"label": "Costo/conversación Popeye", "actual": pop_funnel_wk["actual"]["costoConversacion"], "anterior": pop_funnel_wk["anterior"]["costoConversacion"], "fmt": fmt_clp},
        {"label": "% conversión → reserva Popeye", "actual": pop_funnel_wk["actual"]["pctConversion"], "anterior": pop_funnel_wk["anterior"]["pctConversion"], "fmt": fmt_pct},
    ]

    subject = f"📊 Reporte Meta Ads — {fmt_date_long(report_date)}"

    html = f"""<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:700px;margin:0 auto;color:#1a1a1a;">
  <div style="background:#0b0b0b;color:#fff;padding:20px 24px;border-radius:10px 10px 0 0;">
    <div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#a3a3a3;">Reporte diario · Hotboat</div>
    <div style="font-size:20px;font-weight:700;margin-top:4px;">{fmt_date_long(report_date)}</div>
    <div style="font-size:12px;color:#a3a3a3;margin-top:2px;">El día de ayer se compara contra el promedio ponderado de los últimos 7 días</div>
  </div>

  <div style="border:1px solid #e5e5e5;border-top:none;border-radius:0 0 10px 10px;padding:24px;overflow-x:auto;">

    <h2 style="font-size:15px;margin:0 0 4px;color:#0b0b0b;">🌐 Transbank (web) — CPC por conjunto de anuncios</h2>
    {tb_section['table']}
    {tb_section['summary']}

    <h2 style="font-size:15px;margin:0 0 4px;color:#0b0b0b;">💬 Popeye (WhatsApp) — CPC por conjunto de anuncios</h2>
    {pop_cpc_section['table']}
    {pop_cpc_section['summary']}

    <h2 style="font-size:15px;margin:0 0 10px;color:#0b0b0b;">💬 Popeye (WhatsApp) — embudo de conversación</h2>
    <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:22px;">
      {_header_row(pop_serie)}
      {_build_row('Gasto', pop_serie, 'spend', fmt_clp, total=pop_total['spend'], prom=pop_prom['spend'])}
      {_build_row('Conversaciones', pop_serie, 'conversaciones', fmt_num, total=pop_total['conversaciones'], prom=pop_prom['conversaciones'])}
      {_build_row('Costo/conversación', pop_serie, 'costoConversacion', fmt_clp, prom=pop_prom['costoConversacion'], bold=True, is_rate=True, note='(prom. ponderado)')}
      {_build_row('% conversión → reserva', pop_serie, 'pctConversion', fmt_pct, prom=pop_prom['pctConversion'], is_rate=True)}
      {_build_row('Costo por reserva', pop_serie, 'costoReserva', fmt_clp, prom=pop_prom['costoReserva'], is_rate=True, note='(prom. ponderado)')}
    </table>
    <div style="font-size:12px;color:#525252;margin:-14px 0 20px;">Costo/conversación de ayer {fmt_clp(pop_serie[-1]['costoConversacion'])}{_arrow(popeye_delta)} vs. promedio ponderado de los últimos 7 días {fmt_clp(pop_prom['costoConversacion'])}</div>

    <h2 style="font-size:15px;margin:0 0 4px;color:#0b0b0b;">📈 Semana actual vs. semana anterior</h2>
    <div style="font-size:11.5px;color:#a3a3a3;margin-bottom:8px;">Promedio ponderado: últimos 7 días vs. los 7 días previos a esos (días 8 a 14)</div>
    {_render_week_compare_table(week_compare_rows)}

    <h2 style="font-size:15px;margin:20px 0 10px;color:#0b0b0b;">📅 Negocio</h2>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <tr><td style="padding:6px 0;border-top:1px solid #eee;">Reservas creadas ayer</td><td style="text-align:right;border-top:1px solid #eee;">{no_canceladas}</td></tr>
      <tr><td style="padding:6px 0;">Ingreso asociado</td><td style="text-align:right;">{fmt_clp(ingreso)}</td></tr>
    </table>

    <div style="margin-top:20px;padding-top:16px;border-top:1px solid #eee;font-size:11px;color:#a3a3a3;">
      🔴 = ayer subió/empeoró &gt;15% vs. el promedio ponderado de los últimos 7 días · 🟢 = mejoró &gt;15% · "Total" = suma de los 7 días (— en filas de costo/%, donde sumar no aplica) · "Prom. ponderado" = gasto total / cantidad total de los 7 días · Generado automáticamente
    </div>
  </div>
</div>""".strip()

    text_lines = [
        f"REPORTE META ADS — {fmt_date_long(report_date)}",
        "(últimos 7 días, último = ayer; comparado contra el promedio ponderado de los 7 días)",
        "",
        "TRANSBANK (web) — CPC por conjunto de anuncios",
        _text_group_table("Transbank", tb_by_group),
        "POPEYE (WhatsApp) — CPC por conjunto de anuncios",
        _text_group_table("Popeye", pop_by_group),
        "POPEYE (WhatsApp) — embudo de conversación",
        _text_table(pop_serie, [
            ("Gasto", "spend", fmt_clp, pop_total["spend"], pop_prom["spend"], False),
            ("Conversaciones", "conversaciones", fmt_num, pop_total["conversaciones"], pop_prom["conversaciones"], False),
            ("Costo/conversación (prom. ponderado)", "costoConversacion", fmt_clp, None, pop_prom["costoConversacion"], True),
            ("% conversión->reserva", "pctConversion", fmt_pct, None, pop_prom["pctConversion"], True),
            ("Costo por reserva (prom. ponderado)", "costoReserva", fmt_clp, None, pop_prom["costoReserva"], True),
        ]),
        f"  Costo/conversación ayer {fmt_clp(pop_serie[-1]['costoConversacion'])} vs. promedio ponderado 7 días {fmt_clp(pop_prom['costoConversacion'])}",
        "",
        "SEMANA ACTUAL (últ. 7 días) VS. SEMANA ANTERIOR (días 8-14) — promedio ponderado",
    ]
    for row in week_compare_rows:
        d = _pct_delta(row["actual"], row["anterior"])
        delta_txt = "—" if d is None else f'{"+" if d > 0 else ""}{d:.1f}%'
        text_lines.append(f"  {row['label']}: {row['fmt'](row['actual'])} (semana anterior: {row['fmt'](row['anterior'])}, {delta_txt})")
    text_lines += [
        "",
        "NEGOCIO",
        f"  Reservas creadas ayer: {no_canceladas}",
        f"  Ingreso asociado: {fmt_clp(ingreso)}",
    ]
    text = "\n".join(text_lines)

    return {"subject": subject, "html": html, "text": text}


def send_daily_meta_report() -> None:
    """Generates and emails the report for "yesterday". No dedup table here
    on purpose — this is only ever called from _run_daily_meta_report_scheduler
    in main.py, which (like every other scheduled sweep there) only runs on
    the single replica holding the shared scheduler advisory lock, so it
    already fires exactly once per day across however many replicas are
    running."""
    from app.config import get_settings
    from app.email.send_email import send_email

    settings = get_settings()
    recipients = [e.strip() for e in (settings.notification_emails or "").split(",") if e.strip()]
    if not recipients:
        logger.info("[daily_meta_report] Sin notification_emails configurado, omitiendo")
        return

    # Same from-address fallback chain as booking_email.py's _get_from_addr()
    # — resend_from_confirmations is the actually-verified sender domain;
    # settings.email_from alone can be a placeholder/unverified address (a
    # gmail.com "from" gets rejected by Resend outright, it can only send
    # from a domain you've verified there).
    from_address = (
        (settings.resend_from_confirmations or "").strip()
        or (settings.email_from or "").strip()
        or "onboarding@resend.dev"
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT (CURRENT_DATE - INTERVAL '1 day')::date AS d")
            report_date = cur.fetchone()[0]
            report = generate_report(cur, report_date)

    result = send_email(
        to=recipients,
        subject=report["subject"],
        html=report["html"],
        from_address=from_address,
        trigger="daily_meta_report",
    )
    if result.get("sent"):
        logger.info(f"[daily_meta_report] Enviado a {recipients} ({report_date})")
    else:
        logger.error(f"[daily_meta_report] Envío falló: {result.get('reason')}")
