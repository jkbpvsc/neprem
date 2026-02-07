import argparse
import json
import os
import smtplib
import sys
import time
from dataclasses import dataclass
from email.message import EmailMessage
from csv import DictWriter
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlparse
import re

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


@dataclass(frozen=True)
class Listing:
    url: str
    title: str
    price_eur: str
    location: str
    currency: str = ""
    description: str = ""
    area_m2: str = ""
    year: str = ""
    renovation_year: str = ""
    is_new_building: str = ""
    floor: str = ""
    room_type: str = ""
    listing_type: str = ""
    labels: str = ""
    agency_name: str = ""
    agency_url: str = ""
    agency_phone: str = ""
    images: str = ""
    bedrooms_count: str = ""
    bathrooms_count: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "price_eur": self.price_eur,
            "location": self.location,
            "currency": self.currency,
            "description": self.description,
            "area_m2": self.area_m2,
            "year": self.year,
            "renovation_year": self.renovation_year,
            "is_new_building": self.is_new_building,
            "floor": self.floor,
            "room_type": self.room_type,
            "listing_type": self.listing_type,
            "labels": self.labels,
            "agency_name": self.agency_name,
            "agency_url": self.agency_url,
            "agency_phone": self.agency_phone,
            "images": self.images,
            "bedrooms_count": self.bedrooms_count,
            "bathrooms_count": self.bathrooms_count,
        }


def load_env() -> None:
    load_dotenv()


def get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def normalize_url(base_url: str, href: str) -> str:
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    return parsed._replace(fragment="").geturl()


def fetch_html(base_url: str) -> str:
    use_playwright = get_env("USE_PLAYWRIGHT", "0") == "1"
    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    if use_playwright:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=user_agent)
            page = context.new_page()
            page.goto(base_url, wait_until="networkidle", timeout=60000)
            content = page.content()
            browser.close()
            return content

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    response = session.get(base_url, timeout=20)
    response.raise_for_status()
    return response.text


def parse_number(text: str) -> str:
    if not text:
        return ""
    cleaned = (
        text.replace("\u00a0", " ")
        .replace("€", "")
        .replace("EUR", "")
        .replace("m\u00b2", "")
        .replace("m2", "")
        .strip()
    )
    match = re.findall(r"\d[\d\.,]*", cleaned)
    if not match:
        return ""
    value = match[0]
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        value = value.replace(",", ".")
    return value


def extract_year_built(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    patterns = [
        r"zgr\.\s*l\.\s*(\d{4})",
        r"zgrajen[aо]?\s*l\.\s*(\d{4})",
        r"zgrajeno\s*l\.\s*(\d{4})",
        r"zgrajena\s*l\.\s*(\d{4})",
        r"zgrajen\s*l\.\s*(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return ""


def extract_renovation_year(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    patterns = [
        r"adaptirano\s*l\.\s*(\d{4})",
        r"adaptiran\s*l\.\s*(\d{4})",
        r"adaptirana\s*l\.\s*(\d{4})",
        r"prenovljeno\s*l\.\s*(\d{4})",
        r"prenovljen[aо]?\s*l\.\s*(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return ""


def extract_is_new_building(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower()
    if "novogradnja" in lowered or "novogradnje" in lowered:
        return "1"
    return ""


def is_listing_image(url: str) -> bool:
    if not url:
        return False
    if "img.nepremicnine.net" not in url:
        return False
    if "/slonep_oglasi" not in url:
        return False
    return bool(re.search(r"\.(jpg|jpeg|png|webp)$", url, re.IGNORECASE))


def extract_detail_fields(detail_html: str) -> dict:
    soup = BeautifulSoup(detail_html, "html.parser")
    bedrooms = ""
    bathrooms = ""
    area_m2 = ""
    year = ""
    renovation_year = ""
    is_new_building = ""
    floor = ""
    attributes = [li.get_text(" ", strip=True) for li in soup.select("#atributi li")]
    for text in attributes:
        if text.startswith("Velikost"):
            area_m2 = parse_number(text)
        elif text.startswith("Nadstropje"):
            floor = text.split(":", 1)[-1].strip()
        elif text.startswith("Leto"):
            year = parse_number(text)
        if "Št. spalnic" in text:
            bedrooms = parse_number(text)
        elif "Št. kopalnic" in text:
            bathrooms = parse_number(text)

    meta_desc = soup.select_one("meta[name=Description]")
    meta_text = meta_desc.get("content", "") if meta_desc else ""
    if not year:
        year = extract_year_built(meta_text)
    renovation_year = extract_renovation_year(meta_text)
    is_new_building = extract_is_new_building(meta_text)

    location = ""
    location_block = soup.select_one(".more_info")
    if location_block:
        location_text = " ".join(location_block.get_text(" ", strip=True).split())
        region = re.search(r"Regija:\s*([^|]+)", location_text)
        unit = re.search(r"Upravna enota:\s*([^|]+)", location_text)
        municipality = re.search(r"Občina:\s*([^|]+)", location_text)
        settlement = re.search(r"naselje:\s*([^|]+)", location_text, re.IGNORECASE)
        location = (
            (settlement.group(1).strip() if settlement else "")
            or (municipality.group(1).strip() if municipality else "")
            or (unit.group(1).strip() if unit else "")
            or (region.group(1).strip() if region else "")
        )

    images = []
    for tag in soup.select("a[data-fancybox^='gallery_']"):
        src = tag.get("data-src") or tag.get("href")
        if src and is_listing_image(src):
            images.append(src)

    listing_type = ""
    room_type = ""
    heading = soup.select_one("h1[itemprop=name]")
    if heading:
        heading_text = " ".join(heading.get_text(" ", strip=True).split())
        if " - " in heading_text:
            suffix = heading_text.split(" - ", 1)[1]
            parts = [part.strip() for part in suffix.split(",", 2) if part.strip()]
            if len(parts) >= 2:
                listing_type = parts[1].title()
            if len(parts) >= 3:
                room_type = parts[2]

    return {
        "bedrooms_count": bedrooms,
        "bathrooms_count": bathrooms,
        "area_m2": area_m2,
        "year": year,
        "renovation_year": renovation_year,
        "is_new_building": is_new_building,
        "floor": floor,
        "location": location,
        "images": " | ".join(dict.fromkeys(images)),
        "listing_type": listing_type,
        "room_type": room_type,
    }


def extract_bed_bath_counts(detail_html: str) -> tuple[str, str]:
    fields = extract_detail_fields(detail_html)
    return fields["bedrooms_count"], fields["bathrooms_count"]


def normalize_floor(value: str) -> str:
    if not value:
        return ""
    candidate = value.strip()
    if re.search(r"\bm2\b", candidate, re.IGNORECASE):
        return ""
    return candidate


def get_total_pages(soup: BeautifulSoup) -> int:
    pagination = soup.select_one("#pagination ul[data-pages]")
    if pagination and pagination.get("data-pages"):
        try:
            return int(pagination["data-pages"])
        except ValueError:
            return 1
    return 1


def build_page_url(base_url: str, page: int) -> str:
    if page <= 1:
        return base_url
    if base_url.endswith("/"):
        return f"{base_url}{page}/"
    return f"{base_url}/{page}/"


def scrape_listings(base_url: str, all_pages: bool = False) -> List[Listing]:
    html = fetch_html(base_url)
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and "just a moment" in soup.title.get_text(strip=True).lower():
        raise RuntimeError(
            "Cloudflare check detected. Set USE_PLAYWRIGHT=1 in .env."
        )
    total_pages = get_total_pages(soup) if all_pages else 1
    card_selector = get_env("LISTING_CARD_SELECTOR", ".property-box, .oglas_container, article")
    link_selector = get_env("LISTING_LINK_SELECTOR", "a.url-title-d, a.url-title-m, a[href]")
    title_selector = get_env("LISTING_TITLE_SELECTOR", "a.url-title-d h2, a.url-title-m h2, h2, h3, .title")
    price_selector = get_env("LISTING_PRICE_SELECTOR", "meta[itemprop=price], .price, h6")
    location_selector = get_env(
        "LISTING_LOCATION_SELECTOR",
        ".location, .lokacija, .property-location, .property-details .location",
    )

    listings: List[Listing] = []
    for page in range(1, total_pages + 1):
        if page == 1:
            page_soup = soup
        else:
            page_html = fetch_html(build_page_url(base_url, page))
            page_soup = BeautifulSoup(page_html, "html.parser")

        cards = page_soup.select(card_selector)
        if not cards:
            cards = page_soup.select(".property-box[itemprop='item'], .property-box")
        for card in cards:
            link_tag = card.select_one(link_selector)
            url = ""
            if link_tag and link_tag.get("href"):
                url = normalize_url(base_url, link_tag["href"])
            else:
                meta_url = card.select_one("meta[itemprop=mainEntityOfPage]")
                if meta_url and meta_url.get("content"):
                    url = normalize_url(base_url, meta_url["content"])
            if not url:
                continue

            title_tag = card.select_one(title_selector)
            price_tag = card.select_one(price_selector)
            location_tag = card.select_one(location_selector)

            title = (title_tag.get_text(strip=True) if title_tag else "").strip()
            if price_tag and price_tag.name == "meta":
                price = price_tag.get("content", "").strip()
            else:
                price = (price_tag.get_text(strip=True) if price_tag else "").strip()
            location = (location_tag.get_text(strip=True) if location_tag else "").strip()
            currency_tag = card.select_one("meta[itemprop=priceCurrency]")
            currency = currency_tag.get("content", "").strip() if currency_tag else ""
            price_eur = parse_number(price)

            description_tag = card.select_one("[itemprop=description]")
            description = (
                description_tag.get_text(strip=True) if description_tag else ""
            ).strip()

            labels_list = [
                label.get_text(strip=True)
                for label in card.select(".labels-left span.label")
            ]
            labels = " | ".join(dict.fromkeys([label for label in labels_list if label]))

            listing_type = ""
            room_type = ""
            type_tag = card.select_one(".font-roboto")
            if type_tag:
                type_text = " ".join(type_tag.get_text(" ", strip=True).split())
                # Expected format: "Prodaja: Stanovanje, 3-sobno"
                if ":" in type_text:
                    type_text = type_text.split(":", 1)[1].strip()
                if "," in type_text:
                    listing_type, room_type = [t.strip() for t in type_text.split(",", 1)]
                else:
                    listing_type = type_text.strip()

            area_m2 = ""
            year = ""
            floor = ""
            for li in card.select("[itemprop=disambiguatingDescription] li"):
                img = li.select_one("img")
                alt = img.get("alt", "").strip() if img else ""
                text = li.get_text(" ", strip=True)
                if "Velikost" in alt and not area_m2:
                    area_m2 = parse_number(text)
                elif "Leto" in alt and not year:
                    year = parse_number(text)
                elif "Nad" in alt and not floor:
                    floor = normalize_floor(text.strip())
            if not year:
                year = extract_year_built(description)
            renovation_year = extract_renovation_year(description)
            is_new_building = extract_is_new_building(description)


            agency_name = ""
            agency_url = ""
            agency_phone = ""
            agency_tag = card.select_one("[itemprop=seller] [itemprop=name]")
            if agency_tag:
                agency_name = agency_tag.get("content", "").strip() or agency_tag.get_text(strip=True)
            agency_url_tag = card.select_one("[itemprop=seller] link[itemprop=url]")
            if agency_url_tag and agency_url_tag.get("href"):
                agency_url = agency_url_tag["href"].strip()
            phone_tag = card.select_one("[itemprop=seller] a[href^='tel:']")
            if phone_tag:
                agency_phone = phone_tag.get_text(strip=True)

            image_urls = []
            for img in card.select("img[data-src], img[src]"):
                src = img.get("data-src") or img.get("src")
                if src and is_listing_image(src):
                    image_urls.append(src)
            images = " | ".join(dict.fromkeys(image_urls))

            if not title:
                title = url

            bedrooms_count = ""
            bathrooms_count = ""
            detail_area_m2 = ""
            detail_year = ""
            detail_renovation_year = ""
            detail_is_new_building = ""
            detail_floor = ""
            detail_location = ""
            detail_images = ""
            detail_listing_type = ""
            detail_room_type = ""
            try:
                detail_html = fetch_html(url)
                detail_fields = extract_detail_fields(detail_html)
                bedrooms_count = detail_fields["bedrooms_count"]
                bathrooms_count = detail_fields["bathrooms_count"]
                detail_area_m2 = detail_fields["area_m2"]
                detail_year = detail_fields["year"]
                detail_renovation_year = detail_fields["renovation_year"]
                detail_is_new_building = detail_fields["is_new_building"]
                detail_floor = detail_fields["floor"]
                detail_location = detail_fields["location"]
                detail_images = detail_fields["images"]
                detail_listing_type = detail_fields["listing_type"]
                detail_room_type = detail_fields["room_type"]
            except Exception:
                bedrooms_count = ""
                bathrooms_count = ""

            listings.append(
                Listing(
                    url=url,
                    title=title,
                    price_eur=price_eur,
                    location=detail_location or location,
                    currency=currency,
                    description=description,
                    area_m2=detail_area_m2 or area_m2,
                    year=detail_year or year,
                    renovation_year=detail_renovation_year or renovation_year,
                    is_new_building=detail_is_new_building or is_new_building,
                    floor=detail_floor or floor,
                    room_type=detail_room_type or room_type,
                    listing_type=detail_listing_type or listing_type,
                    labels=labels,
                    agency_name=agency_name,
                    agency_url=agency_url,
                    agency_phone=agency_phone,
                    images=detail_images or images,
                    bedrooms_count=bedrooms_count,
                    bathrooms_count=bathrooms_count,
                )
            )

    # Fallback: dedupe by URL while preserving order
    seen_urls = set()
    unique_listings: List[Listing] = []
    for listing in listings:
        if listing.url in seen_urls:
            continue
        seen_urls.add(listing.url)
        unique_listings.append(listing)

    return unique_listings


def load_seen(path: str) -> set:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return set(data)
    except (OSError, json.JSONDecodeError):
        return set()
    return set()


def save_seen(path: str, urls: Iterable[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(sorted(set(urls)), handle, indent=2, ensure_ascii=False)


def send_stdout(listings: List[Listing]) -> None:
    for listing in listings:
        parts = [listing.title]
        if listing.price_eur:
            parts.append(listing.price_eur)
        if listing.location:
            parts.append(listing.location)
        parts.append(listing.url)
        print(" | ".join(parts))


def send_smtp(listings: List[Listing]) -> None:
    host = get_env("SMTP_HOST")
    user = get_env("SMTP_USER")
    password = get_env("SMTP_PASS")
    port = int(get_env("SMTP_PORT", "587") or "587")
    sender = get_env("SMTP_FROM")
    recipient = get_env("SMTP_TO")

    if not all([host, user, password, sender, recipient]):
        raise RuntimeError("SMTP settings are incomplete.")

    body_lines = []
    for listing in listings:
        line = f"{listing.title} | {listing.price_eur} | {listing.location} | {listing.url}"
        body_lines.append(line)

    message = EmailMessage()
    message["Subject"] = f"{len(listings)} new listing(s) on nepremicnine.net"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("\n".join(body_lines))

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(message)


def notify(listings: List[Listing]) -> None:
    mode = get_env("NOTIFY_MODE", "stdout").lower()
    if mode == "smtp":
        send_smtp(listings)
    else:
        send_stdout(listings)


def run_once(data_path: str, base_url: str) -> int:
    listings = scrape_listings(base_url)
    seen = load_seen(data_path)
    new_listings = [listing for listing in listings if listing.url not in seen]

    if new_listings:
        notify(new_listings)
        seen.update(listing.url for listing in new_listings)
        save_seen(data_path, seen)
        return 0

    return 1


def print_listings(base_url: str) -> int:
    listings = scrape_listings(base_url)
    payload = [listing.to_dict() for listing in listings]
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def write_csv(base_url: str, output_path: str, all_pages: bool = False) -> int:
    listings = scrape_listings(base_url, all_pages=all_pages)
    rows = [listing.to_dict() for listing in listings]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else list(Listing("", "", "", "").to_dict().keys())
    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(output_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Nepremicnine listing notifier.")
    parser.add_argument("--loop", action="store_true", help="Keep running forever.")
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Polling interval in seconds when --loop is set.",
    )
    parser.add_argument(
        "--data-path",
        default=os.path.join(os.path.dirname(__file__), "data", "seen.json"),
        help="Path to store seen listing URLs.",
    )
    parser.add_argument(
        "--url",
        default="",
        help="Override the base URL to scrape.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the current listings as JSON and exit.",
    )
    parser.add_argument(
        "--csv",
        default="",
        help="Write listings to a CSV file and exit.",
    )
    parser.add_argument(
        "--all-pages",
        action="store_true",
        help="Scrape all paginated result pages.",
    )
    args = parser.parse_args()

    load_env()
    base_url = args.url.strip() or get_env("BASE_URL", "https://www.nepremicnine.net/")
    if not base_url:
        print("BASE_URL is missing.", file=sys.stderr)
        return 2

    if args.list:
        return print_listings(base_url)
    if args.csv:
        return write_csv(base_url, args.csv, all_pages=args.all_pages)

    if not args.loop:
        return run_once(args.data_path, base_url)

    while True:
        run_once(args.data_path, base_url)
        time.sleep(max(args.interval, 30))


if __name__ == "__main__":
    raise SystemExit(main())
