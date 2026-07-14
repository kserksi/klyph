from dataclasses import replace

import pytest

import app.main as main_module
from app.config import settings


def test_default_network_configuration_is_domain_neutral():
    assert settings.public_base_url == "http://localhost:8000"
    assert settings.allowed_origins == (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    )


def test_https_deployment_can_use_any_domain():
    configured = replace(
        settings,
        public_base_url="https://fonts.example.com",
        allowed_origins=("https://www.example.com",),
    )

    assert configured.public_base_url == "https://fonts.example.com"
    assert configured.allowed_origins == ("https://www.example.com",)


def test_non_loopback_http_deployment_is_rejected():
    with pytest.raises(ValueError, match="must use HTTPS"):
        replace(settings, public_base_url="http://fonts.example.com")


def test_non_loopback_http_origin_is_rejected():
    with pytest.raises(ValueError, match="invalid allowed origin"):
        replace(settings, allowed_origins=("http://www.example.com",))


def test_public_metadata_uses_configured_domain(monkeypatch):
    configured = replace(settings, public_base_url="https://fonts.example.com")
    monkeypatch.setattr(main_module, "settings", configured)
    main_module.public_text_asset.cache_clear()
    try:
        html = main_module.public_html_response("index.html", 300).body.decode()
        robots = main_module.public_text_asset("robots.txt")
        sitemap = main_module.public_text_asset("sitemap.xml")
    finally:
        main_module.public_text_asset.cache_clear()

    assert '<link rel="canonical" href="https://fonts.example.com/">' in html
    assert "{{PUBLIC_BASE_URL}}" not in html
    assert "Sitemap: https://fonts.example.com/sitemap.xml" in robots
    assert "<loc>https://fonts.example.com/</loc>" in sitemap
