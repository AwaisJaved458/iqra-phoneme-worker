# Vendored from https://github.com/RamsesAguirre777/facebook-ads-library-mcp
# (MIT License, commit d8eed5a) with two fixes so it runs against current deps
# and the real Graph API response shapes:
#   - crawl4ai >= 0.7 removed the sync WebCrawler; snapshot scraping now uses
#     AsyncWebCrawler when available and falls back to requests+BeautifulSoup.
#   - impressions/spend arrive as {"lower_bound", "upper_bound"} objects, not
#     strings; all aggregation goes through _range_midpoint().
from fastmcp import FastMCP
import requests
import json
import sys
import os
from datetime import datetime
from typing import List
import re

BASE_URL = "https://graph.facebook.com/v19.0/ads_archive"


def _range_midpoint(value) -> float:
    """Midpoint of a Graph API insight range ({"lower_bound","upper_bound"} or legacy string)."""
    if isinstance(value, dict):
        try:
            lo = float(str(value.get("lower_bound", 0) or 0).replace(",", ""))
            hi = float(str(value.get("upper_bound", lo) or lo).replace(",", ""))
            return (lo + hi) / 2
        except (TypeError, ValueError):
            return 0.0
    if isinstance(value, str):
        numbers = re.findall(r"\d+", value.replace(",", ""))
        if numbers:
            return sum(int(n) for n in numbers) / len(numbers)
    return 0.0


class FacebookAdsLibraryAPI:
    """Facebook Ads Library API wrapper"""

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _make_request(self, params: dict) -> dict:
        """Make API request with error handling"""
        params = dict(params)
        params["access_token"] = self.access_token
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            detail = ""
            if getattr(e, "response", None) is not None:
                try:
                    detail = e.response.json().get("error", {}).get("message", "")
                except ValueError:
                    detail = e.response.text[:300]
            return {"error": f"{e} — {detail}".strip(" —"), "success": False}

    def _extract_ad_id_from_url(self, snapshot_url: str) -> str:
        match = re.search(r"id=(\d+)", snapshot_url)
        return match.group(1) if match else None

    def _analyze_ad_creative(self, snapshot_url: str) -> dict:
        """Scrape an ad snapshot page. Uses crawl4ai when installed, else requests+bs4."""
        try:
            import asyncio
            from crawl4ai import AsyncWebCrawler

            async def _crawl():
                async with AsyncWebCrawler() as crawler:
                    return await crawler.arun(url=snapshot_url)

            result = asyncio.run(_crawl())
            return {
                "text_content": result.cleaned_html or "",
                "extracted_text": str(result.markdown or ""),
                "success": True,
            }
        except ImportError:
            pass
        except Exception as e:
            return {"error": str(e), "success": False}

        try:
            from bs4 import BeautifulSoup

            html = requests.get(snapshot_url, timeout=30).text
            text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            return {"text_content": html, "extracted_text": text, "success": True}
        except Exception as e:
            return {"error": str(e), "success": False}


mcp = FastMCP(
    name="Facebook Ads Library",
    instructions="""
    Facebook Ads Library MCP with tools for competitive ad intelligence:
    searching the Ad Library, discovering competitors, analyzing creatives,
    estimating spend, comparing brands, and exporting data.
    """,
)


def get_facebook_token():
    """Get Facebook access token from command line arguments or environment"""
    if "--facebook-token" in sys.argv:
        token_index = sys.argv.index("--facebook-token") + 1
        if token_index < len(sys.argv):
            return sys.argv[token_index]
    return os.getenv("FACEBOOK_ACCESS_TOKEN")


fb_api = FacebookAdsLibraryAPI(get_facebook_token())

# ===== SEARCH & DISCOVERY =====


@mcp.tool(description="Search Facebook Ads Library with advanced filters")
def search_facebook_ads(
    brand_name: str,
    country: str = "US",
    ad_type: str = "ALL",
    date_range: int = 30,
    limit: int = 50,
) -> dict:
    """
    Search Facebook Ads Library with comprehensive filters

    Args:
        brand_name: Brand or company name to search
        country: Target country code (US, GB, CA, etc.)
        ad_type: Type of ads (ALL, POLITICAL_AND_ISSUE_ADS, etc.)
        date_range: Days to look back (default: 30)
        limit: Maximum number of ads to return
    """
    params = {
        "search_terms": brand_name,
        "ad_reached_countries": json.dumps([country]),
        "fields": "id,ad_creation_time,ad_creative_bodies,ad_creative_link_captions,ad_creative_link_descriptions,ad_creative_link_titles,ad_snapshot_url,currency,demographic_distribution,delivery_by_region,impressions,page_id,page_name,publisher_platforms,spend",
        "limit": limit,
        "ad_active_status": "ALL",
    }

    if ad_type != "ALL":
        params["ad_type"] = ad_type

    result = fb_api._make_request(params)

    if result.get("success") is False:
        return result

    return {
        "brand": brand_name,
        "total_ads": len(result.get("data", [])),
        "ads": result.get("data", []),
        "success": True,
    }


@mcp.tool(description="Discover competitor brands in an industry")
def discover_competitor_brands(
    industry_keywords: str,
    region: str = "US",
    min_ads: int = 5,
    limit: int = 100,
) -> dict:
    """
    Discover competitor brands by industry keywords

    Args:
        industry_keywords: Industry-related keywords (e.g., "fitness app", "food delivery")
        region: Target region
        min_ads: Minimum number of ads to qualify as active advertiser
        limit: Maximum brands to return
    """
    params = {
        "search_terms": industry_keywords,
        "ad_reached_countries": json.dumps([region]),
        "fields": "page_name,page_id,ad_creation_time",
        "limit": min(limit * 3, 300),
        "ad_active_status": "ACTIVE",
    }

    result = fb_api._make_request(params)

    if result.get("success") is False:
        return result

    brand_counts = {}
    for ad in result.get("data", []):
        page_name = ad.get("page_name", "")
        if page_name:
            brand_counts[page_name] = brand_counts.get(page_name, 0) + 1

    qualified_brands = {
        brand: count for brand, count in brand_counts.items() if count >= min_ads
    }
    sorted_brands = sorted(qualified_brands.items(), key=lambda x: x[1], reverse=True)

    return {
        "industry": industry_keywords,
        "region": region,
        "discovered_brands": sorted_brands[:limit],
        "total_qualified_brands": len(qualified_brands),
        "success": True,
    }


@mcp.tool(description="Analyze ad creative elements in detail")
def analyze_ad_creative_elements(
    ad_snapshot_url: str,
    extract_text: bool = True,
    analyze_images: bool = True,
    detect_cta: bool = True,
) -> dict:
    """
    Deep analysis of ad creative elements

    Args:
        ad_snapshot_url: URL to Facebook ad snapshot
        extract_text: Extract all text content
        analyze_images: Analyze image elements
        detect_cta: Detect call-to-action elements
    """
    creative_analysis = fb_api._analyze_ad_creative(ad_snapshot_url)

    if not creative_analysis.get("success"):
        return creative_analysis

    analysis_result = {
        "ad_url": ad_snapshot_url,
        "ad_id": fb_api._extract_ad_id_from_url(ad_snapshot_url),
        "analysis": {},
    }

    text_content = creative_analysis.get("extracted_text", "")

    if extract_text:
        analysis_result["analysis"]["text_analysis"] = {
            "word_count": len(text_content.split()),
            "character_count": len(text_content),
            "sentiment_keywords": re.findall(
                r"\b(?:amazing|best|free|save|new|limited|exclusive|now)\b",
                text_content.lower(),
            ),
            "full_text": text_content,
        }

    if detect_cta:
        cta_patterns = [
            r"\b(?:shop now|buy now|learn more|sign up|download|get started|try free|claim offer)\b",
            r"\b(?:click here|tap here|swipe up|see more|order now|book now)\b",
        ]

        detected_ctas = []
        for pattern in cta_patterns:
            detected_ctas.extend(re.findall(pattern, text_content.lower()))

        analysis_result["analysis"]["cta_analysis"] = {
            "detected_ctas": detected_ctas,
            "cta_count": len(detected_ctas),
            "urgency_words": re.findall(
                r"\b(?:now|today|limited|hurry|urgent|expires|deadline)\b",
                text_content.lower(),
            ),
        }

    analysis_result["success"] = True
    return analysis_result


@mcp.tool(description="Analyze ad performance metrics and insights")
def analyze_ad_performance_metrics(
    brand_name: str,
    time_period: int = 30,
    performance_metrics: List[str] = None,
) -> dict:
    """
    Analyze ad performance metrics for a brand

    Args:
        brand_name: Brand name to analyze
        time_period: Analysis period in days
        performance_metrics: Specific metrics to analyze
    """
    params = {
        "search_terms": brand_name,
        "ad_reached_countries": json.dumps(["US"]),
        "fields": "id,ad_creation_time,impressions,spend,demographic_distribution,delivery_by_region,publisher_platforms,currency",
        "limit": 100,
        "ad_active_status": "ALL",
    }

    result = fb_api._make_request(params)

    if result.get("success") is False:
        return result

    ads = result.get("data", [])

    total_impressions = 0.0
    total_spend = 0.0
    platform_distribution = {}
    demographic_summary = {}

    for ad in ads:
        total_impressions += _range_midpoint(ad.get("impressions"))
        total_spend += _range_midpoint(ad.get("spend"))

        for platform in ad.get("publisher_platforms", []):
            platform_distribution[platform] = platform_distribution.get(platform, 0) + 1

        for demo in ad.get("demographic_distribution", []):
            age_gender = f"{demo.get('age', 'unknown')}_{demo.get('gender', 'unknown')}"
            demographic_summary[age_gender] = demographic_summary.get(age_gender, 0) + 1

    return {
        "brand": brand_name,
        "analysis_period": f"{time_period} days",
        "total_ads_analyzed": len(ads),
        "performance_summary": {
            "estimated_total_impressions": total_impressions,
            "estimated_total_spend": total_spend,
            "platform_distribution": platform_distribution,
            "demographic_distribution": demographic_summary,
            "avg_impressions_per_ad": total_impressions / len(ads) if ads else 0,
            "avg_spend_per_ad": total_spend / len(ads) if ads else 0,
        },
        "success": True,
    }


@mcp.tool(description="Comprehensive competitive ad analysis")
def competitive_ad_analysis(
    brands_list: List[str],
    metrics_comparison: List[str] = None,
    analysis_depth: str = "standard",
) -> dict:
    """
    Compare ad strategies across multiple competitor brands

    Args:
        brands_list: List of brand names to compare
        metrics_comparison: Specific metrics to compare
        analysis_depth: Depth of analysis (standard, deep)
    """
    comparison_results = {}

    for brand in brands_list:
        brand_data = search_facebook_ads(brand, limit=50)

        if not brand_data.get("success"):
            continue

        ads = brand_data.get("ads", [])
        brand_analysis = {
            "total_ads": len(ads),
            "active_ads": len([ad for ad in ads if "ad_creation_time" in ad]),
            "platforms": set(),
            "estimated_spend": 0.0,
            "creative_themes": [],
        }

        for ad in ads:
            brand_analysis["platforms"].update(ad.get("publisher_platforms", []))
            brand_analysis["estimated_spend"] += _range_midpoint(ad.get("spend"))

            for body in ad.get("ad_creative_bodies", []):
                words = body.lower().split()
                themes = [word for word in words if len(word) > 5 and word.isalpha()]
                brand_analysis["creative_themes"].extend(themes[:3])

        brand_analysis["platforms"] = list(brand_analysis["platforms"])
        brand_analysis["creative_themes"] = list(set(brand_analysis["creative_themes"]))[:10]
        comparison_results[brand] = brand_analysis

    insights = {
        "market_leader": max(comparison_results.items(), key=lambda x: x[1]["total_ads"])[0]
        if comparison_results
        else None,
        "highest_spender": max(comparison_results.items(), key=lambda x: x[1]["estimated_spend"])[0]
        if comparison_results
        else None,
        "platform_trends": {},
        "common_themes": [],
    }

    all_platforms = {}
    for brand, data in comparison_results.items():
        for platform in data["platforms"]:
            all_platforms[platform] = all_platforms.get(platform, 0) + 1
    insights["platform_trends"] = dict(
        sorted(all_platforms.items(), key=lambda x: x[1], reverse=True)
    )

    all_themes = []
    for brand, data in comparison_results.items():
        all_themes.extend(data["creative_themes"])
    theme_counts = {}
    for theme in all_themes:
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
    insights["common_themes"] = [t for t, c in theme_counts.items() if c > 1][:10]

    return {
        "brands_analyzed": brands_list,
        "comparison_results": comparison_results,
        "competitive_insights": insights,
        "analysis_timestamp": datetime.now().isoformat(),
        "success": True,
    }


@mcp.tool(description="Generate comprehensive Facebook ads intelligence report")
def generate_facebook_intelligence_report(
    brand_name: str,
    include_competitors: bool = True,
    report_depth: str = "comprehensive",
) -> dict:
    """
    Generate complete intelligence report for a brand's Facebook advertising

    Args:
        brand_name: Primary brand to analyze
        include_competitors: Include competitor analysis
        report_depth: Depth of report (basic, standard, comprehensive)
    """
    report = {
        "brand": brand_name,
        "report_timestamp": datetime.now().isoformat(),
        "analysis_summary": {},
        "detailed_findings": {},
        "recommendations": [],
        "success": True,
    }

    try:
        basic_ads = search_facebook_ads(brand_name, limit=100)
        report["analysis_summary"]["total_ads"] = basic_ads.get("total_ads", 0)

        performance = analyze_ad_performance_metrics(brand_name)
        report["detailed_findings"]["performance_metrics"] = performance.get(
            "performance_summary", {}
        )

        recent_ads = [ad for ad in basic_ads.get("ads", []) if ad.get("ad_creation_time")]
        report["detailed_findings"]["recent_activity"] = {
            "total_recent_ads": len(recent_ads),
            "avg_ads_per_week": len(recent_ads) / 4 if recent_ads else 0,
        }

        platforms = {}
        for ad in basic_ads.get("ads", []):
            for platform in ad.get("publisher_platforms", []):
                platforms[platform] = platforms.get(platform, 0) + 1
        report["detailed_findings"]["platform_distribution"] = platforms

        if include_competitors:
            competitors = discover_competitor_brands(brand_name)
            top_competitors = [
                brand for brand, count in competitors.get("discovered_brands", [])[:5]
            ]
            if top_competitors:
                competitive_analysis = competitive_ad_analysis([brand_name] + top_competitors)
                report["detailed_findings"]["competitive_landscape"] = competitive_analysis.get(
                    "competitive_insights", {}
                )

        recommendations = []
        if report["analysis_summary"]["total_ads"] < 10:
            recommendations.append("Consider increasing ad volume for better market presence")
        if "instagram" not in platforms and "facebook" in platforms:
            recommendations.append("Expand to Instagram for broader reach")
        if len(recent_ads) < 5:
            recommendations.append("Increase creative refresh rate for better performance")
        report["recommendations"] = recommendations

        report["analysis_summary"].update(
            {
                "ad_activity_level": "High"
                if len(recent_ads) > 10
                else "Medium"
                if len(recent_ads) > 5
                else "Low",
                "platform_diversity": len(platforms),
                "primary_platform": max(platforms.items(), key=lambda x: x[1])[0]
                if platforms
                else "Unknown",
                "competitive_position": "Analysis included"
                if include_competitors
                else "Not analyzed",
            }
        )

    except Exception as e:
        report["success"] = False
        report["error"] = str(e)

    return report


@mcp.tool(description="Export Facebook ads data to various formats")
def export_facebook_ads_data(
    brand_name: str,
    export_format: str = "json",
    include_creatives: bool = False,
    limit: int = 100,
) -> dict:
    """
    Export Facebook ads data in various formats

    Args:
        brand_name: Brand to export data for
        export_format: Format for export (json, csv, markdown)
        include_creatives: Include creative analysis
        limit: Maximum number of ads to export
    """
    ads_data = search_facebook_ads(brand_name, limit=limit)

    if not ads_data.get("success"):
        return ads_data

    ads = ads_data.get("ads", [])
    export_data = []

    for ad in ads:
        ad_record = {
            "ad_id": ad.get("id"),
            "page_name": ad.get("page_name"),
            "creation_time": ad.get("ad_creation_time"),
            "impressions": ad.get("impressions"),
            "spend": ad.get("spend"),
            "currency": ad.get("currency"),
            "creative_bodies": ad.get("ad_creative_bodies", []),
            "platforms": ad.get("publisher_platforms", []),
            "snapshot_url": ad.get("ad_snapshot_url"),
        }

        if include_creatives and ad.get("ad_snapshot_url"):
            creative_analysis = analyze_ad_creative_elements(ad["ad_snapshot_url"])
            ad_record["creative_analysis"] = creative_analysis.get("analysis", {})

        export_data.append(ad_record)

    if export_format == "json":
        formatted_data = json.dumps(export_data, indent=2, default=str)
    elif export_format == "csv":
        csv_lines = ["id,page_name,creation_time,impressions,spend,platforms"]
        for record in export_data:
            csv_lines.append(
                f"{record['ad_id']},{record['page_name']},{record['creation_time']},"
                f"{_range_midpoint(record['impressions'])},{_range_midpoint(record['spend'])},"
                f"{';'.join(record['platforms'])}"
            )
        formatted_data = "\n".join(csv_lines)
    elif export_format == "markdown":
        md_lines = [
            "# Facebook Ads Export",
            f"## Brand: {brand_name}",
            "",
            "| Ad ID | Page Name | Creation Time | Impressions | Spend | Platforms |",
            "|-------|-----------|---------------|-------------|-------|-----------|",
        ]
        for record in export_data:
            md_lines.append(
                f"| {record['ad_id']} | {record['page_name']} | {record['creation_time']} | "
                f"{_range_midpoint(record['impressions'])} | {_range_midpoint(record['spend'])} | "
                f"{', '.join(record['platforms'])} |"
            )
        formatted_data = "\n".join(md_lines)
    else:
        formatted_data = export_data

    return {
        "brand": brand_name,
        "export_format": export_format,
        "total_records": len(export_data),
        "export_data": formatted_data,
        "export_timestamp": datetime.now().isoformat(),
        "success": True,
    }


if __name__ == "__main__":
    token = get_facebook_token()
    if not token:
        print("❌ Facebook access token required!")
        print("Usage: python facebook_ads_mcp.py --facebook-token YOUR_TOKEN")
        print("   or: export FACEBOOK_ACCESS_TOKEN=YOUR_TOKEN")
        sys.exit(1)

    print("✅ Facebook Ads Library MCP Server starting...")
    mcp.run(transport="stdio")
