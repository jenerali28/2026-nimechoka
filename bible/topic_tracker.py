#!/usr/bin/env python3
"""
Topic Tracker — Bible Story Deduplication.

Maintains a JSON registry of used Bible story topics so the pipeline
never generates the same story twice (even if titles differ).

Uses fuzzy matching on normalized topic strings to catch variations
like "David na Goliath" vs "Vita vya Daudi na Goliathi".
"""

import json
import re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TRACKER_FILE = Path(__file__).parent / "used_topics.json"

# Curated list of Bible stories popular with East African / Tanzanian audience.
# Mix of Old & New Testament — dramatic, well-known narratives.
BIBLE_STORIES = [
    # --- Agano la Kale (Old Testament) ---
    "Uumbaji wa Dunia na Adamu na Hawa",
    "Adamu na Hawa katika Bustani ya Edeni",
    "Kaini na Abeli — Mauaji ya Kwanza",
    "Nuhu na Gharika Kuu",
    "Mnara wa Babeli",
    "Wito wa Abrahamu — Safari ya Imani",
    "Abrahamu na Isaka — Jaribio la Imani",
    "Yakobo na Esau — Mapambano ya Ndugu",
    "Yakobo Anapigana na Malaika",
    "Yusufu Anauzwa na Ndugu Zake",
    "Yusufu Mfasiri wa Ndoto za Farao",
    "Yusufu Anakutana Tena na Ndugu Zake",
    "Musa Mchanga Aokolewa Mtoni",
    "Musa na Kichaka Kinachowaka Moto",
    "Mapigo Kumi ya Misri",
    "Kutoka Misri — Kuvuka Bahari ya Shamu",
    "Amri Kumi za Mungu Mlimani Sinai",
    "Waisraeli na Ndama wa Dhahabu",
    "Waisraeli Jangwani — Miaka Arobaini",
    "Rahab na Wapelelezi wa Yeriko",
    "Kuanguka kwa Kuta za Yeriko",
    "Gideoni na Askari Mia Tatu",
    "Samsoni na Delila",
    "Ruthu na Naomi — Uaminifu wa Ajabu",
    "Samueli Mdogo Aitwa na Mungu",
    "Daudi na Goliathi",
    "Ufalme wa Mfalme Daudi",
    "Daudi na Bathsheba — Kutenda Dhambi",
    "Hekima ya Mfalme Sulemani",
    "Sulemani na Wanawake Wawili — Hukumu ya Hekima",
    "Hekalu la Sulemani",
    "Nabii Eliya na Manabii wa Baali",
    "Eliya Akimbia Jangwani — Mungu Anazungumza Kimya",
    "Elisha na Mwanamke wa Shunemu",
    "Naaman Aponywa Ukoma",
    "Danieli katika Tundu la Simba",
    "Shadraka Meshaki na Abednego katika Tanuru la Moto",
    "Yona na Nyangumi Mkubwa",
    "Esther Anaokoa Taifa Lake",
    "Ayubu — Kustahimili Mateso Makubwa",
    "Nehemia Ajenga Upya Ukuta wa Yerusalemu",
    "Isaya Atabiri Kuja kwa Masihi",
    "Yeremia — Nabii Aliyelia",
    "Ezekieli na Bonde la Mifupa Mikavu",

    # --- Agano Jipya (New Testament) ---
    "Kuzaliwa kwa Yesu Bethlehemu",
    "Mamajusi Watatu Wanatembelea Mtoto Yesu",
    "Herode na Mauaji ya Watoto Wachanga",
    "Yesu Mdogo Hekaluni — Miaka 12",
    "Ubatizo wa Yesu Mtoni Yordani",
    "Yesu Anajaribiwa Jangwani Siku 40",
    "Yesu Achagua Wanafunzi 12",
    "Muujiza wa Kwanza — Maji Kuwa Divai Kana",
    "Yesu Anatembea Juu ya Maji",
    "Yesu Analisha Watu Elfu Tano",
    "Yesu Anaponya Mtu Aliyezaliwa Kipofu",
    "Yesu Anafufua Lazaro kutoka Wafu",
    "Mfano wa Mpanzi na Mbegu",
    "Mfano wa Mwana Mpotevu",
    "Mfano wa Msamaria Mwema",
    "Mfano wa Talanta — Kutumia Karama",
    "Mfano wa Wanawali Kumi — Kujiandaa",
    "Yesu na Mwanamke Kisimani",
    "Yesu Anaponya Wagonjwa Wengi",
    "Yesu Anafukuza Wafanyabiashara Hekaluni",
    "Yesu Anatokeza Juu ya Mlima — Kubadilika Sura",
    "Karamu ya Mwisho",
    "Bustani ya Gethsemane — Sala ya Mwisho",
    "Kusaliti kwa Yuda Iskariote",
    "Petro Anamkana Yesu Mara Tatu",
    "Mahakama ya Yesu mbele ya Pilato",
    "Kusulubiwa kwa Yesu Kalvari",
    "Yesu Anafufuka — Kaburi Tupu",
    "Tomaso Asiyeamini — Ushahidi wa Ufufuko",
    "Yesu Anapaa Mbinguni",
    "Siku ya Pentekoste — Roho Mtakatifu Anashuka",
    "Sauli wa Tarso Anageuka — Safari ya Dameski",
    "Paulo na Sila Gerezani — Kuimba Usiku wa Manane",
    "Paulo Anaeneza Injili kwa Mataifa",
    "Ufunuo wa Yohana — Maono ya Mbinguni",

    # --- Extended dramatic stories ---
    "Loti na Uharibifu wa Sodoma na Gomora",
    "Musa Anapasua Bahari — Ushindi wa Mungu",
    "Balamu na Punda Aliyezungumza",
    "Yoshua Anasimamisha Jua",
    "Debora — Mwanamke Shujaa wa Israeli",
    "Mfalme Sauli na Wito Wake",
    "Absalomu Anaasi Dhidi ya Baba Yake Daudi",
    "Nabii Eliya Anapanda Mbinguni kwa Gari la Moto",
    "Mmea wa Yona — Somo la Huruma",
    "Danieli na Ndoto za Mfalme Nebukadneza",
    "Malaika Jibrili Amtembelea Mariamu",
    "Yesu Anaponya Mwenye Kupooza — Kupitia Paa",
    "Simoni Petro Avua Samaki Wengi",
    "Dorkasi Afufuliwa na Petro",
    "Petro Aachiliwa Gerezani na Malaika",
    "Kornelio — Watu wa Mataifa Wanakubaliwa",
    "Stefano — Shahidi wa Kwanza wa Kanisa",
    "Filipo na Towashi wa Ethiopia",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalize a topic string for comparison."""
    text = text.lower().strip()
    # Remove common Swahili articles/connectors for fuzzy matching
    text = re.sub(r'\b(na|wa|ya|la|za|kwa|katika|au|ni)\b', ' ', text)
    # Remove punctuation and extra whitespace
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_key_names(text: str) -> set[str]:
    """Extract likely proper names (capitalized words) from topic text."""
    words = text.split()
    names = set()
    for w in words:
        # Keep words that start with uppercase and are >2 chars
        clean = re.sub(r'[^\w]', '', w)
        if clean and clean[0].isupper() and len(clean) > 2:
            names.add(clean.lower())
    return names


def _topics_match(topic_a: str, topic_b: str) -> bool:
    """Check if two topics refer to the same Bible story."""
    norm_a = _normalize(topic_a)
    norm_b = _normalize(topic_b)

    # Direct normalized match
    if norm_a == norm_b:
        return True

    # Check if one contains the other
    if norm_a in norm_b or norm_b in norm_a:
        return True

    # Check key name overlap (proper nouns)
    names_a = _extract_key_names(topic_a)
    names_b = _extract_key_names(topic_b)
    if names_a and names_b:
        overlap = names_a & names_b
        # If >60% of the smaller set's names match, it's likely the same story
        min_set_size = min(len(names_a), len(names_b))
        if min_set_size > 0 and len(overlap) / min_set_size >= 0.6:
            return True

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_used_topics() -> list[dict]:
    """Load the used topics registry."""
    if not TRACKER_FILE.exists():
        return []
    try:
        data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def save_topic(topic: str, title: str) -> None:
    """Record a topic as used."""
    used = load_used_topics()
    used.append({
        "topic": topic,
        "title": title,
        "created_at": datetime.now().isoformat(),
    })
    TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRACKER_FILE.write_text(json.dumps(used, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  📝 Topic saved: {topic}")


def is_topic_used(topic: str) -> bool:
    """Check if a topic (or a very similar one) has already been used."""
    used = load_used_topics()
    for entry in used:
        if _topics_match(topic, entry["topic"]):
            return True
    return False


def get_suggested_topics(count: int, exclude: list[str] | None = None) -> list[str]:
    """Return up to `count` unused Bible story topics.

    Checks both the persistent tracker file AND any additional
    topics passed in `exclude`.
    """
    used = load_used_topics()
    exclude = exclude or []

    available = []
    for story in BIBLE_STORIES:
        # Skip if in persistent tracker
        already_used = any(_topics_match(story, u["topic"]) for u in used)
        # Skip if in the current session's exclude list
        session_used = any(_topics_match(story, e) for e in exclude)
        if not already_used and not session_used:
            available.append(story)

    return available[:count]


# ---------------------------------------------------------------------------
# CLI for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Bible Topic Tracker")
    parser.add_argument("--suggest", type=int, default=5, help="Show N suggested topics")
    parser.add_argument("--used", action="store_true", help="List all used topics")
    parser.add_argument("--check", type=str, help="Check if a topic is already used")

    args = parser.parse_args()

    if args.used:
        for entry in load_used_topics():
            print(f"  • {entry['topic']} → {entry['title']} ({entry['created_at']})")
    elif args.check:
        result = is_topic_used(args.check)
        print(f"  {'✅ Already used' if result else '❌ Not used'}: {args.check}")
    else:
        topics = get_suggested_topics(args.suggest)
        print(f"📖 {len(topics)} suggested Bible stories:")
        for i, t in enumerate(topics, 1):
            print(f"  {i}. {t}")
