import re
import logging
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from .base import CachedHttpClient
from ..models import (
    HackathonEvent,
    JudgingCriterion,
    PrizeCategory,
    RawProject,
    ProjectLink,
    ProjectTeamMember,
    DescriptionSections,
    ProvenanceRecord,
    EvidenceType,
)

logger = logging.getLogger("hackbench.devpost")


class DevpostCollector:
    """
    Scrapes and parses hackathon event metadata and project submissions from Devpost.
    Preserves raw evidence and source provenance.
    """

    def __init__(self, http_client: CachedHttpClient):
        self.client = http_client

    def ingest_event(self, event_url: str) -> HackathonEvent:
        """
        Parses hackathon homepage for event overview, prizes, rules, criteria, and dates.
        """
        # Normalize event URL
        parsed = urlparse(event_url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
        html = self.client.get(event_url)
        soup = BeautifulSoup(html, "html.parser")

        # Extract event title
        title_el = soup.select_one("#challenge-title, h1.title, meta[property='og:title']")
        title = ""
        if title_el:
            title = title_el.get("content") if title_el.name == "meta" else title_el.get_text(strip=True)
        if not title:
            title = parsed.netloc.split(".")[0].capitalize()

        # Extract year
        year_match = re.search(r"202\d", f"{title} {event_url}")
        year = int(year_match.group(0)) if year_match else 2025

        slug = parsed.netloc.split(".")[0].lower()
        if not slug or slug == "devpost":
            slug = f"hackathon-{year}"

        gallery_url = urljoin(base_origin, "/project-gallery")

        # Judging criteria
        criteria: List[JudgingCriterion] = []
        criteria_section = soup.select("#judging-criteria article, #criteria .criterion, #judging-criteria .row")
        for crit in criteria_section:
            c_name = crit.select_one("h6, strong, h5, .criterion-title")
            c_desc = crit.select_one("p, .criterion-description")
            if c_name:
                name_text = c_name.get_text(strip=True)
                desc_text = c_desc.get_text(strip=True) if c_desc else ""
                criteria.append(
                    JudgingCriterion(
                        name=name_text,
                        description=desc_text,
                        source_url=event_url,
                    )
                )

        # Prizes / Sponsor challenges
        prizes: List[PrizeCategory] = []
        sponsor_technologies = set()
        prize_elements = soup.select(".prize, #prizes .columns, .prize-item")
        for p_el in prize_elements:
            p_id = p_el.get("id", "")
            title_tag = p_el.select_one(".prize-title, h6, h5, h4")
            if not title_tag:
                continue
            p_title = title_tag.get_text(strip=True)
            if not p_title or len(p_title) < 2:
                continue

            desc_tag = p_el.select_one(".prize-content p, .prize-description, p")
            desc_text = desc_tag.get_text(strip=True) if desc_tag else ""

            winners_tag = p_el.select_one(".prize-winners, .winners-count")
            winners_count = 1
            if winners_tag:
                w_match = re.search(r"(\d+)\s+winner", winners_tag.get_text(strip=True), re.I)
                if w_match:
                    winners_count = int(w_match.group(1))

            # Classify prize type
            p_lower = p_title.lower()
            p_type = "track"
            sponsor_name = None

            if "best overall" in p_lower or "overall" in p_lower or "1st" in p_lower or "first place" in p_lower:
                p_type = "overall"
            elif "beginner" in p_lower or "first-time" in p_lower or "first time" in p_lower:
                p_type = "beginner"
            elif "people's choice" in p_lower or "community" in p_lower:
                p_type = "peoples_choice"
            elif any(kw in p_lower for kw in ["sponsor", "by ", "&", "api", "challenge", "powered by"]):
                p_type = "sponsor"
                # extract potential sponsor name
                sponsor_match = re.search(r"(?:by\s+|sponsored by\s+)([\w\s\.]+)", p_title, re.I)
                if sponsor_match:
                    sponsor_name = sponsor_match.group(1).strip()
            
            prizes.append(
                PrizeCategory(
                    prize_id=p_id or f"prize_{len(prizes)+1}",
                    title=p_title,
                    prize_type=p_type,
                    sponsor_name=sponsor_name,
                    description=desc_text,
                    number_of_winners=winners_count,
                    source_url=event_url,
                )
            )

        # Dates / schedule
        dates_el = soup.select_one(".challenge-details time, .submission-period, meta[property='og:description']")
        dates_str = dates_el.get_text(strip=True) if dates_el else ""

        # Number of submissions / gallery check
        num_projects = None
        try:
            gallery_html = self.client.get(gallery_url)
            g_soup = BeautifulSoup(gallery_html, "html.parser")
            pag_info = g_soup.select_one(".pagination-info")
            if pag_info:
                match = re.search(r"of\s+(\d+)", pag_info.get_text())
                if match:
                    num_projects = int(match.group(1))
        except Exception as e:
            logger.warning(f"Could not fetch gallery count: {e}")

        provenance = [
            ProvenanceRecord(
                claim=f"Hackathon {title} ingested from Devpost",
                evidence_type=EvidenceType.EVENT_RULES,
                source=event_url,
                location="event-homepage",
                confidence=1.0,
            )
        ]

        return HackathonEvent(
            name=title,
            slug=slug,
            year=year,
            organizer="INIT / FIU" if "shellhacks" in slug else "Hackathon Organizers",
            event_url=event_url,
            devpost_url=event_url,
            gallery_url=gallery_url,
            judging_criteria=criteria,
            prize_categories=prizes,
            number_of_projects=num_projects,
            sources=provenance,
        )

    def discover_gallery_projects(
        self, gallery_url: str, max_pages: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Paginates through /project-gallery, discovering all submitted projects.
        """
        discovered: List[Dict[str, Any]] = []
        page = 1

        while True:
            if max_pages and page > max_pages:
                break

            page_url = f"{gallery_url}?page={page}" if page > 1 else gallery_url
            try:
                html = self.client.get(page_url)
            except Exception as e:
                logger.error(f"Failed to fetch gallery page {page}: {e}")
                break

            soup = BeautifulSoup(html, "html.parser")
            gallery_items = soup.select(".gallery-item")
            if not gallery_items:
                # No more items on this page
                break

            logger.info(f"Gallery page {page}: found {len(gallery_items)} projects.")

            for item in gallery_items:
                software_id = item.get("data-software-id")
                link_el = item.select_one("a.link-to-software")
                if not link_el:
                    continue
                software_url = link_el.get("href", "")
                if not software_url:
                    continue

                title_el = item.select_one(".entry-body h5, h5")
                title = title_el.get_text(strip=True) if title_el else ""

                tagline_el = item.select_one(".entry-body p, p.tagline")
                tagline = tagline_el.get_text(strip=True) if tagline_el else ""

                # Thumbnail
                thumb_el = item.select_one("img.software_thumbnail_image, img")
                thumb_url = thumb_el.get("src", "") if thumb_el else ""

                # Winner badge presence (kept strictly for outcome extraction staging)
                badge_el = item.select_one("aside.entry-badge, .winner")
                has_winner_badge = bool(badge_el and "winner" in badge_el.get_text().lower())

                discovered.append({
                    "software_id": software_id or software_url.split("/")[-1],
                    "title": title,
                    "url": software_url,
                    "tagline": tagline,
                    "thumbnail_url": thumb_url,
                    "gallery_winner_badge": has_winner_badge,
                    "gallery_page": page,
                })

            # Check next page link
            next_page = soup.select_one(".pagination .next_page:not(.unavailable)")
            if not next_page:
                break
            page += 1

        return discovered

    def fetch_project_details(
        self,
        software_url: str,
        software_id: str,
        gallery_info: Optional[Dict[str, Any]] = None,
    ) -> RawProject:
        """
        Parses project detail page on Devpost into a RawProject model.
        """
        html = self.client.get(software_url)
        soup = BeautifulSoup(html, "html.parser")

        title_el = soup.select_one("h1#app-title")
        title = title_el.get_text(strip=True) if title_el else (gallery_info.get("title") if gallery_info else "")
        if not title:
            title = software_url.split("/")[-1].replace("-", " ").title()

        tagline_el = soup.select_one("p.large")
        tagline = tagline_el.get_text(strip=True) if tagline_el else (gallery_info.get("tagline", "") if gallery_info else "")

        # Description sections
        sections = DescriptionSections()
        app_details = soup.select_one("#app-details-left")
        full_text = []

        if app_details:
            current_heading = "general"
            current_content: List[str] = []

            for child in app_details.children:
                if child.name in ["h2", "h3"]:
                    # Save previous section
                    text_block = "\n".join(current_content).strip()
                    self._assign_section(sections, current_heading, text_block)
                    current_heading = child.get_text(strip=True).lower()
                    current_content = []
                elif child.name in ["p", "ul", "ol", "div", "blockquote"]:
                    t = child.get_text(strip=True)
                    if t:
                        current_content.append(t)
                        full_text.append(t)

            # Assign final section
            if current_content:
                text_block = "\n".join(current_content).strip()
                self._assign_section(sections, current_heading, text_block)

        sections.raw_full_text = "\n\n".join(full_text)

        # Tech tags
        tech_tags = [
            tag.get_text(strip=True)
            for tag in soup.select("#built-with li span.cp-tag, #built-with li a")
            if tag.get_text(strip=True)
        ]

        # External Links
        links: List[ProjectLink] = []
        github_urls: List[str] = []
        demo_urls: List[str] = []
        deployment_urls: List[str] = []

        for a in soup.select("ul[data-role=software-urls] a, #app-details a[href]"):
            href = a.get("href", "").strip()
            if not href or href.startswith("#") or "devpost.com/software/built-with" in href:
                continue

            link_title = a.get_text(strip=True)
            lower_href = href.lower()

            if "github.com" in lower_href or "gitlab.com" in lower_href or "bitbucket.org" in lower_href:
                link_type = "github"
                if href not in github_urls:
                    github_urls.append(href)
            elif any(v in lower_href for v in ["youtube.com", "youtu.be", "vimeo.com", "loom.com"]):
                link_type = "youtube"
                if href not in demo_urls:
                    demo_urls.append(href)
            elif "figma.com" in lower_href:
                link_type = "figma"
                if href not in demo_urls:
                    demo_urls.append(href)
            elif any(d in lower_href for d in ["vercel.app", "netlify.app", "onrender.com", "herokuapp.com", "base44.app"]):
                link_type = "deployment"
                if href not in deployment_urls:
                    deployment_urls.append(href)
            else:
                link_type = "other"

            links.append(ProjectLink(url=href, link_type=link_type, title=link_title))

        # Check for embedded iframe video players
        for iframe in soup.select("iframe[src]"):
            src = iframe.get("src", "")
            if any(v in src.lower() for v in ["youtube.com", "youtu.be", "vimeo.com", "loom.com"]):
                if src not in demo_urls:
                    demo_urls.append(src)
                links.append(ProjectLink(url=src, link_type="youtube", title="Embedded Video Demo"))

        # Team members
        team_members: List[ProjectTeamMember] = []
        for member_el in soup.select("#app-details-right .user-profile-link, #app-details-right li a[href*='/users/']"):
            profile_url = member_el.get("href", "")
            img_el = member_el.select_one("img")
            name = img_el.get("alt", "") if img_el else member_el.get_text(strip=True)
            username = profile_url.rstrip("/").split("/")[-1] if profile_url else ""
            if name and not any(m.name == name for m in team_members):
                team_members.append(
                    ProjectTeamMember(name=name, devpost_username=username, profile_url=profile_url)
                )

        # Winner awards on project page (kept strictly for outcome extraction)
        raw_winner_awards: List[str] = []
        for li in soup.select("#app-details-right ul.no-bullet li, #app-details-right .winner"):
            text = li.get_text(strip=True)
            if "winner" in text.lower():
                # Clean up "Winner" prefix to get award name
                clean_award = re.sub(r"^Winner\s*", "", text, flags=re.I).strip()
                if clean_award and clean_award not in raw_winner_awards:
                    raw_winner_awards.append(clean_award)

        has_gallery_winner = gallery_info.get("gallery_winner_badge", False) if gallery_info else False

        slug = software_url.rstrip("/").split("/")[-1]
        thumb_url = gallery_info.get("thumbnail_url", "") if gallery_info else ""

        provenance = [
            ProvenanceRecord(
                claim="Project details ingested from Devpost",
                evidence_type=EvidenceType.DEVPOST,
                source=software_url,
                location="#app-details",
                confidence=1.0,
            )
        ]

        return RawProject(
            project_id=software_id,
            slug=slug,
            title=title,
            devpost_url=software_url,
            gallery_url=gallery_info.get("gallery_url", "") if gallery_info else "",
            tagline=tagline,
            description_sections=sections,
            tech_tags=tech_tags,
            links=links,
            github_urls=github_urls,
            demo_urls=demo_urls,
            deployment_urls=deployment_urls,
            team_members=team_members,
            team_size=len(team_members) if team_members else 1,
            thumbnail_url=thumb_url,
            gallery_winner_badge=has_gallery_winner,
            raw_winner_awards_text=raw_winner_awards,
            provenance=provenance,
        )

    def _assign_section(self, sections: DescriptionSections, heading: str, content: str):
        h = heading.lower()
        if "problem" in h or "background" in h:
            sections.problem_statement = content
        elif "inspiration" in h or "why we built" in h:
            sections.inspiration = content
        elif "what it does" in h or "about the project" in h:
            sections.what_it_does = content
        elif "how we built" in h or "how it was built" in h or "technologies" in h:
            sections.how_it_was_built = content
        elif "challenges" in h:
            sections.challenges = content
        elif "accomplishments" in h or "what we're proud" in h:
            sections.accomplishments = content
        elif "what we learned" in h or "lessons" in h:
            sections.lessons_learned = content
        elif "what's next" in h or "future" in h:
            sections.future_plans = content
