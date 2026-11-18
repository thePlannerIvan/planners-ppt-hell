"""Non-default canvases keep preview and pointer movement in SVG coordinates."""
import unittest
import test_workbench_ui as harness

class CanvasBrowserTests(harness.WorkbenchBrowserTests):
    def portrait(self):
        self.page.evaluate('''() => {
          const svg=currentSvgRoot();
          svg.setAttribute('width','1080');svg.setAttribute('height','1920');
          svg.setAttribute('viewBox','0 0 1080 1920');sizePreview();
        }''')

    def test_portrait_preview_uses_selected_svg_aspect(self):
        self.portrait()
        box=self.page.locator('#preview').bounding_box()
        self.assertAlmostEqual(box['width']/box['height'],1080/1920,places=2)

    def test_portrait_drag_uses_svg_coordinates(self):
        self.portrait()
        self.page.evaluate("() => {marking=false;document.querySelector('#preview').classList.remove('marking');}")
        box=self.page.locator('#preview').bounding_box()
        title=self.page.locator('#svgStageWrap text').first.bounding_box()
        x=title['x']+title['width']/2;y=title['y']+title['height']/2
        self.page.keyboard.down('Alt')  # Measure free drag, not a nearby alignment target.
        self.page.mouse.move(x,y);self.page.mouse.down()
        self.page.mouse.move(x+box['width']/10,y+box['height']/10,steps=5)
        edits=self.page.evaluate('() => state[page().key].svg_edits')
        self.page.mouse.up()
        self.page.keyboard.up('Alt')
        self.assertTrue(edits)
        self.assertAlmostEqual(edits[-1]['dx'],108,delta=2)
        self.assertAlmostEqual(edits[-1]['dy'],192,delta=2)

def load_tests(loader, tests, pattern):
    return unittest.TestSuite(CanvasBrowserTests(name) for name in (
        'test_portrait_preview_uses_selected_svg_aspect', 'test_portrait_drag_uses_svg_coordinates'))
