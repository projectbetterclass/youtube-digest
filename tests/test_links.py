"""Link extraction + classification (no network)."""

from ytdigest.links import classify_links, classify_url, extract_urls


def test_extract_urls_dedups_and_trims_trailing_punctuation():
    text = "See https://example.com/a.pdf. Also (https://example.com/b) and https://example.com/a.pdf again"
    urls = extract_urls(text)
    assert urls == ["https://example.com/a.pdf", "https://example.com/b"]


def test_downloadable_documents():
    assert classify_url("https://example.com/deck.pdf").kind == "download"
    assert classify_url("https://example.com/deck.pdf").category == "pdf"
    assert classify_url("https://example.com/slides.pptx").category == "pptx"
    assert classify_url("https://speakerdeck.com/user/talk").category == "speakerdeck"
    assert classify_url("https://www.slideshare.net/user/talk").category == "slideshare"
    for u in ("https://example.com/deck.pdf", "https://speakerdeck.com/user/talk"):
        assert classify_url(u).kind == "download"


def test_mention_only_links():
    assert classify_url("https://github.com/foo/bar").kind == "list"
    assert classify_url("https://github.com/foo/bar").category == "github"
    assert classify_url("https://arxiv.org/abs/2408.00001").category == "paper"
    assert classify_url("https://example.com/some-article").category == "other"
    # Non-https document is listed, never downloaded.
    insecure = classify_url("http://example.com/deck.pdf")
    assert insecure.kind == "list"
    assert insecure.category == "pdf"


def test_excel_documents_downloadable():
    assert classify_url("https://example.com/model.xlsx").kind == "download"
    assert classify_url("https://example.com/model.xlsx").category == "excel"
    assert classify_url("https://example.com/model.xls").category == "excel"
    assert classify_url("https://example.com/model.xlsm").category == "excel"


def test_trusted_http_host_allows_download():
    # Aswath's NYU pages serve slides/spreadsheets over plain http on older pages.
    pdf = classify_url("http://www.stern.nyu.edu/~adamodar/pdfiles/cfovhds/ProjSumm20.pdf")
    assert pdf.kind == "download" and pdf.category == "pdf"
    xls = classify_url("http://www.stern.nyu.edu/~adamodar/pc/cfanalysis/cfspr20.xlsx")
    assert xls.kind == "download" and xls.category == "excel"
    # A subdomain of the trusted registered domain is also allowed.
    assert classify_url("http://pages.stern.nyu.edu/~adamodar/apv.xls").kind == "download"
    # But http from an untrusted host stays mention-only.
    assert classify_url("http://example.com/model.xlsx").kind == "list"
    assert classify_url("http://example.com/model.xlsx").category == "excel"


def test_classify_description_buckets():
    desc = (
        "Slides: https://example.com/talk-deck.pdf\n"
        "Code: https://github.com/example/neural-render\n"
        "Preprint: https://arxiv.org/abs/2408.00001"
    )
    links = classify_links(desc)
    downloads = [ln for ln in links if ln.kind == "download"]
    listed = [ln for ln in links if ln.kind == "list"]
    assert [ln.category for ln in downloads] == ["pdf"]
    assert {ln.category for ln in listed} == {"github", "paper"}
