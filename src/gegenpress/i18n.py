"""Four languages, one gate.

The brief asks for insights "for fans around the world in multiple
languages". The interesting part is not the translation; it is that
translating costs this system nothing in verifiability.

The Gate extracts numbers from what Desk wrote and checks each one
against the brief. Numbers are not a language. So the same control holds
over Spanish, French and Arabic output without a second verifier, a
second set of thresholds, or a model call per language -- which is the
opposite of what happens to a fact-checker that is itself a model, where
every new language is a new place to be wrong in.

Two constraints follow from that and are deliberate:

* Western digits in every language, including Arabic. Arabic-Indic
  numerals would still satisfy the Gate's regex -- Python's `\\d` is
  Unicode-aware -- but Western digits are what Arabic sports broadcast
  actually uses, and keeping one numeral set means the figure on screen
  is the figure in the payload in every locale.
* The templates are deterministic, like the English ones. Nothing here
  goes near a translation API, so a claim never leaves the region it was
  computed in. That is a data-residency property, not a cost saving.

The Arabic here is broadcast-register Modern Standard Arabic and should
be read by a native speaker before anyone relies on it commercially.
"""

from __future__ import annotations

# code, endonym, text direction
LANGUAGES: tuple[tuple[str, str, str], ...] = (
    ("en", "English", "ltr"),
    ("es", "Español", "ltr"),
    ("fr", "Français", "ltr"),
    ("ar", "العربية", "rtl"),
    # Not a language: a register. Same grounded claim, no jargon -- the
    # idea F1 ships as a beginner mode. It costs one row here because the
    # Gate checks digits, so plain English is held to the same control as
    # the broadcast register and needs no separate verifier.
    ("en-simple", "Plain English", "ltr"),
)

LANGUAGE_CODES: tuple[str, ...] = tuple(c for c, _, _ in LANGUAGES)
DIRECTION: dict[str, str] = {c: d for c, _, d in LANGUAGES}


# --------------------------------------------------------------------------
# Metric vocabulary
# --------------------------------------------------------------------------
# Keyed by the metric key, not by the English label: translating a
# translation is how "ball speed" becomes "speed of the ball game".

METRICS: dict[str, dict[str, str]] = {
    "en": {
        "recovery_time_s": "recovery time",
        "pass_difficulty": "pass difficulty",
        "pass_distance_m": "pass range",
        "ball_speed_ms": "ball speed",
        "top_speed_ms": "top speed",
        "carry_distance_m": "carry range",
        "shot_speed_ms": "shot speed",
        "xg": "shot quality",
    },
    "es": {
        "recovery_time_s": "tiempo de recuperación",
        "pass_difficulty": "dificultad del pase",
        "pass_distance_m": "alcance de pase",
        "ball_speed_ms": "velocidad del balón",
        "top_speed_ms": "velocidad máxima",
        "carry_distance_m": "distancia de conducción",
        "shot_speed_ms": "velocidad de disparo",
        "xg": "calidad de disparo",
    },
    "fr": {
        "recovery_time_s": "temps de récupération",
        "pass_difficulty": "difficulté de passe",
        "pass_distance_m": "portée de passe",
        "ball_speed_ms": "vitesse de balle",
        "top_speed_ms": "vitesse maximale",
        "carry_distance_m": "distance de conduite",
        "shot_speed_ms": "vitesse de tir",
        "xg": "qualité de tir",
    },
    "en-simple": {
        "recovery_time_s": "how fast he wins the ball back",
        "pass_difficulty": "how hard his passes are",
        "pass_distance_m": "how far he passes",
        "ball_speed_ms": "how hard he strikes it",
        "top_speed_ms": "how fast he runs",
        "carry_distance_m": "how far he runs with it",
        "shot_speed_ms": "how hard he shoots",
        "xg": "how good his chances are",
    },
    "ar": {
        "recovery_time_s": "زمن استخلاص الكرة",
        "pass_difficulty": "صعوبة التمرير",
        "pass_distance_m": "مدى التمرير",
        "ball_speed_ms": "سرعة الكرة",
        "top_speed_ms": "السرعة القصوى",
        "carry_distance_m": "مسافة حمل الكرة",
        "shot_speed_ms": "سرعة التسديد",
        "xg": "جودة التسديد",
    },
}


# --------------------------------------------------------------------------
# The claim Desk writes
# --------------------------------------------------------------------------

_MOMENT_WITH_NORM: dict[str, str] = {
    "en": "{minute}' {player}: {metric} {value} tonight, against a season norm of {norm}.",
    "es": "{minute}' {player}: {metric} {value} esta noche, frente a una media de temporada de {norm}.",
    "fr": "{minute}' {player} : {metric} {value} ce soir, contre une moyenne de saison de {norm}.",
    "ar": "{minute}' {player}: {metric} {value} الليلة، مقابل معدل موسمي قدره {norm}.",
    "en-simple": "{minute}' {player} — {metric}: {value} tonight. He normally manages about {norm}.",
}

_MOMENT_BARE: dict[str, str] = {
    "en": "{minute}' {player}: {metric} {value}.",
    "es": "{minute}' {player}: {metric} {value}.",
    "fr": "{minute}' {player} : {metric} {value}.",
    "ar": "{minute}' {player}: {metric} {value}.",
    "en-simple": "{minute}' {player} — {metric}: {value} tonight.",
}


# The Form Line claim, in its three shapes: up on his own norm, down on
# it, or level with it.
_CLAIM_ABOVE: dict[str, str] = {
    "en": "{player}: {metric} {value}{unit} tonight against a season norm of {norm}{unit} ({z} SD over {n} matches).",
    "es": "{player}: {metric} {value}{unit} esta noche frente a una media de temporada de {norm}{unit} ({z} DE en {n} partidos).",
    "fr": "{player} : {metric} {value}{unit} ce soir contre une moyenne de saison de {norm}{unit} ({z} ET sur {n} matchs).",
    "ar": "{player}: {metric} {value}{unit} الليلة مقابل معدل موسمي قدره {norm}{unit} ({z} انحراف معياري عبر {n} مباراة).",
    "en-simple": "{player} — {metric}: {value}{unit} tonight, better than the {norm}{unit} he normally manages across {n} matches.",
}

_CLAIM_BELOW: dict[str, str] = {
    "en": "{player}: {metric} down to {value}{unit} from a season norm of {norm}{unit} ({z} SD over {n} matches).",
    "es": "{player}: {metric} baja a {value}{unit} desde una media de temporada de {norm}{unit} ({z} DE en {n} partidos).",
    "fr": "{player} : {metric} en baisse à {value}{unit} depuis une moyenne de saison de {norm}{unit} ({z} ET sur {n} matchs).",
    "ar": "{player}: {metric} تراجع إلى {value}{unit} من معدل موسمي قدره {norm}{unit} ({z} انحراف معياري عبر {n} مباراة).",
    "en-simple": "{player} — {metric}: only {value}{unit} tonight, below the {norm}{unit} he normally manages across {n} matches.",
}

_CLAIM_LEVEL: dict[str, str] = {
    "en": "{player}: {metric} {value}{unit}, in line with his season norm.",
    "es": "{player}: {metric} {value}{unit}, en línea con su media de temporada.",
    "fr": "{player} : {metric} {value}{unit}, conforme à sa moyenne de saison.",
    "ar": "{player}: {metric} {value}{unit}، في حدود معدله الموسمي.",
    "en-simple": "{player} — {metric}: {value}{unit} tonight, about normal for him.",
}


def form_claim(
    lang: str,
    *,
    player: str,
    metric_key: str,
    value: str,
    norm: str,
    z: str,
    appearances: int,
    unit: str = "",
    direction: str = "level",
) -> str:
    table = {"above": _CLAIM_ABOVE, "below": _CLAIM_BELOW}.get(direction, _CLAIM_LEVEL)
    tpl = table.get(lang, table["en"])
    return tpl.format(
        player=player,
        metric=metric_label(metric_key, lang),
        value=value,
        norm=norm,
        z=z,
        n=appearances,
        unit=unit,
    )


def metric_label(metric_key: str, lang: str = "en") -> str:
    table = METRICS.get(lang, METRICS["en"])
    return table.get(metric_key, METRICS["en"].get(metric_key, metric_key))


def moment_text(
    lang: str,
    *,
    minute: int | str,
    player: str,
    metric_key: str,
    value: str,
    norm: str | None = None,
) -> str:
    """One grounded sentence. Same digits in every language, by design."""
    label = metric_label(metric_key, lang)
    tpl = (_MOMENT_WITH_NORM if norm else _MOMENT_BARE).get(
        lang, (_MOMENT_WITH_NORM if norm else _MOMENT_BARE)["en"]
    )
    return tpl.format(
        minute=minute, player=player, metric=label, value=value, norm=norm
    )


# --------------------------------------------------------------------------
# Console chrome
# --------------------------------------------------------------------------
# Only strings the viewer reads. Keys match the data attributes in
# docs/index.html so a missing translation falls back visibly in tests
# rather than invisibly on air.

UI: dict[str, dict[str, str]] = {
    "en": {
        "live_now": "now",
        "goal": "GOAL",
        "live_poss": "POSS",
        "live_passes": "PASSES",
        "live_shots": "SHOTS",
        "live_recov": "RECOV",
        "try_nonumbers": "NOTHING TO CHECK — the gate reads numbers, not sentences",
        "try_btn": "Try to break it",
        "try_title": "Try to make it lie",
        "try_hint": "Write a sentence about this player. Every number in it is checked against what was measured.",
        "try_check": "Check",
        "try_rejected": "REJECTED",
        "try_allowed": "ALLOWED — every number checks out",
        "try_instead": "What it will say instead",
        "try_unsupported": "not measured",
        "live": "LIVE",
        "form_line": "FORM LINE",
        "above": "ABOVE HIS LEVEL",
        "below": "BELOW HIS LEVEL",
        "in_line": "IN LINE WITH HIS OWN NORM",
        "ordinary": "ORDINARY LEAGUE-WIDE",
        "tonight": "TONIGHT",
        "league": "LEAGUE",
        "his_norm": "HIS NORM",
        "beaten": "beaten · norm",
        "matches": "matches",
        "moments": "Moments",
        "follow": "Follow — lift over own norm",
        "signal": "Personal claims allowed — ICC ≥ 0.08",
        "personal": "personal",
        "league_only": "league only",
        "why": "Why",
        "measured": "MEASURED",
        "his_season": "HIS SEASON",
        "gate": "GATE",
        "play": "Play",
        "pause": "Pause",
        "wide": "Wide",
        "sound": "Sound",
        "analyst": "Analyst",
        "fan": "Fan",
    },
    "es": {
        "live_now": "ahora",
        "goal": "GOL",
        "live_poss": "POS.",
        "live_passes": "PASES",
        "live_shots": "TIROS",
        "live_recov": "RECUP.",
        "try_nonumbers": "NADA QUE COMPROBAR — el filtro lee números, no frases",
        "try_btn": "Intenta romperlo",
        "try_title": "Intenta hacerle mentir",
        "try_hint": "Escribe una frase sobre este jugador. Cada número se comprueba contra lo medido.",
        "try_check": "Comprobar",
        "try_rejected": "RECHAZADO",
        "try_allowed": "PERMITIDO — todos los números cuadran",
        "try_instead": "Lo que dirá en su lugar",
        "try_unsupported": "no medido",
        "live": "EN VIVO",
        "form_line": "LÍNEA DE FORMA",
        "above": "POR ENCIMA DE SU NIVEL",
        "below": "POR DEBAJO DE SU NIVEL",
        "in_line": "EN LÍNEA CON SU PROPIA MEDIA",
        "ordinary": "NORMAL EN LA LIGA",
        "tonight": "ESTA NOCHE",
        "league": "LIGA",
        "his_norm": "SU MEDIA",
        "beaten": "supera · media",
        "matches": "partidos",
        "moments": "Momentos",
        "follow": "Seguir — mejora sobre su media",
        "signal": "Afirmaciones personales permitidas — ICC ≥ 0,08",
        "personal": "personal",
        "league_only": "solo liga",
        "why": "Por qué",
        "measured": "MEDIDO",
        "his_season": "SU TEMPORADA",
        "gate": "FILTRO",
        "play": "Reproducir",
        "pause": "Pausa",
        "wide": "Amplio",
        "sound": "Sonido",
        "analyst": "Analista",
        "fan": "Aficionado",
    },
    "fr": {
        "live_now": "maintenant",
        "goal": "BUT",
        "live_poss": "POSS.",
        "live_passes": "PASSES",
        "live_shots": "TIRS",
        "live_recov": "RÉCUP.",
        "try_nonumbers": "RIEN À VÉRIFIER — le filtre lit des chiffres, pas des phrases",
        "try_btn": "Essayez de le casser",
        "try_title": "Essayez de le faire mentir",
        "try_hint": "Écrivez une phrase sur ce joueur. Chaque chiffre est vérifié contre ce qui a été mesuré.",
        "try_check": "Vérifier",
        "try_rejected": "REJETÉ",
        "try_allowed": "AUTORISÉ — tous les chiffres concordent",
        "try_instead": "Ce qu'il dira à la place",
        "try_unsupported": "non mesuré",
        "live": "EN DIRECT",
        "form_line": "LIGNE DE FORME",
        "above": "AU-DESSUS DE SON NIVEAU",
        "below": "EN DESSOUS DE SON NIVEAU",
        "in_line": "CONFORME À SA PROPRE MOYENNE",
        "ordinary": "ORDINAIRE DANS LE CHAMPIONNAT",
        "tonight": "CE SOIR",
        "league": "CHAMPIONNAT",
        "his_norm": "SA MOYENNE",
        "beaten": "dépasse · moyenne",
        "matches": "matchs",
        "moments": "Moments",
        "follow": "Suivre — écart au-dessus de sa moyenne",
        "signal": "Affirmations personnelles autorisées — ICC ≥ 0,08",
        "personal": "personnel",
        "league_only": "championnat seulement",
        "why": "Pourquoi",
        "measured": "MESURÉ",
        "his_season": "SA SAISON",
        "gate": "FILTRE",
        "play": "Lecture",
        "pause": "Pause",
        "wide": "Large",
        "sound": "Son",
        "analyst": "Analyste",
        "fan": "Supporter",
    },
    "en-simple": {
        "live_now": "right now",
        "goal": "GOAL",
        "live_poss": "HAD THE BALL",
        "live_passes": "PASSES",
        "live_shots": "SHOTS",
        "live_recov": "WON IT BACK",
        "try_nonumbers": "NOTHING TO CHECK — it only checks numbers",
        "try_btn": "Try to break it",
        "try_title": "Try to make it lie",
        "try_hint": "Write a sentence about this player. Every number gets checked against what was actually measured.",
        "try_check": "Check",
        "try_rejected": "NO — IT WON'T SAY THAT",
        "try_allowed": "FINE — every number is real",
        "try_instead": "What it will say instead",
        "try_unsupported": "nobody measured this",
        "live": "LIVE",
        "form_line": "HOW HE'S DOING",
        "above": "BETTER THAN USUAL FOR HIM",
        "below": "WORSE THAN USUAL FOR HIM",
        "in_line": "ABOUT NORMAL FOR HIM",
        "ordinary": "AVERAGE FOR THE LEAGUE",
        "tonight": "TONIGHT",
        "league": "EVERYONE ELSE",
        "his_norm": "USUALLY",
        "beaten": "better than · average",
        "matches": "matches",
        "moments": "Worth a look",
        "follow": "Watch these — playing above their usual",
        "signal": "Which stats can be about one player — ICC ≥ 0.08",
        "personal": "about him",
        "league_only": "league only",
        "why": "Why",
        "measured": "WE MEASURED",
        "his_season": "HIS USUAL",
        "gate": "CHECKED",
        "play": "Play",
        "pause": "Pause",
        "wide": "Wide",
        "sound": "Sound",
        "analyst": "Analyst",
        "fan": "New fan",
    },
    "ar": {
        "live_now": "الآن",
        "goal": "هدف",
        "live_poss": "استحواذ",
        "live_passes": "تمريرات",
        "live_shots": "تسديدات",
        "live_recov": "استخلاص",
        "try_nonumbers": "لا شيء للتحقق منه — البوابة تقرأ الأرقام لا الجمل",
        "try_btn": "حاول كسره",
        "try_title": "حاول أن تجعله يكذب",
        "try_hint": "اكتب جملة عن هذا اللاعب. كل رقم فيها يُقارن بما تم قياسه.",
        "try_check": "تحقق",
        "try_rejected": "مرفوض",
        "try_allowed": "مقبول — كل الأرقام صحيحة",
        "try_instead": "ما سيقوله بدلاً من ذلك",
        "try_unsupported": "غير مقاس",
        "live": "مباشر",
        "form_line": "خط المستوى",
        "above": "فوق مستواه المعتاد",
        "below": "دون مستواه المعتاد",
        "in_line": "في حدود معدله المعتاد",
        "ordinary": "عادي على مستوى الدوري",
        "tonight": "الليلة",
        "league": "الدوري",
        "his_norm": "معدله",
        "beaten": "يتجاوز · المعدل",
        "matches": "مباراة",
        "moments": "اللقطات",
        "follow": "المتابعة — التفوق على معدله",
        "signal": "الادعاءات الشخصية المسموح بها — ICC ≥ 0.08",
        "personal": "شخصي",
        "league_only": "الدوري فقط",
        "why": "لماذا",
        "measured": "المقاس",
        "his_season": "موسمه",
        "gate": "البوابة",
        "play": "تشغيل",
        "pause": "إيقاف",
        "wide": "عريض",
        "sound": "الصوت",
        "analyst": "محلل",
        "fan": "مشجع",
    },
}


def ui(lang: str) -> dict[str, str]:
    """Chrome for one language, English-filled so nothing renders blank."""
    base = dict(UI["en"])
    base.update(UI.get(lang, {}))
    return base
