"""Screenshot each .slide of bluegreen_carousel.html to out/carousel/slide_N.png (1080x1350)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

from prototypes.reel_v2._browser import launch

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "carousel"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = launch(p)
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        pg.goto((HERE / "bluegreen_carousel.html").as_uri())
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(300)
        for i, s in enumerate(pg.query_selector_all(".slide"), 1):
            s.screenshot(path=str(OUT / f"slide_{i}.png"))
            over = pg.evaluate("""i => { const s = document.querySelectorAll('.slide')[i], q = s.getBoundingClientRect();
                return [...s.querySelectorAll('*')].filter(e => { const r = e.getBoundingClientRect();
                  return r.bottom > q.bottom + 1 || r.right > q.right + 1; }).map(e => e.className || e.tagName).slice(0, 5); }""", i - 1)
            print(i, "overflow:", over)
        b.close()


if __name__ == "__main__":
    main()
