from bs4 import BeautifulSoup

from job_hunter.interview_prep.html_text import extract_visible_text


def test_extract_visible_text_strips_boilerplate_tags():
    html = """
    <html><body>
    <nav>Home About</nav>
    <header>Site Header</header>
    <main><h1>Job Title</h1><p>We need a great engineer.</p></main>
    <footer>Copyright 2026</footer>
    <script>var x = 1;</script>
    <style>.a{color:red}</style>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")

    text = extract_visible_text(soup)

    assert "Job Title" in text
    assert "We need a great engineer." in text
    assert "Home About" not in text
    assert "Site Header" not in text
    assert "Copyright 2026" not in text
    assert "var x = 1" not in text
    assert "color:red" not in text


def test_extract_visible_text_truncates_to_max_chars():
    html = "<html><body><p>" + ("word " * 2000) + "</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")

    text = extract_visible_text(soup, max_chars=50)

    assert len(text) == 50
