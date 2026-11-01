import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]/"site"
class CoverageUiTests(unittest.TestCase):
 def test_quality_tab_contains_unique_coverage_panel(self):
  html=(SITE/"research_hub_30a.html").read_text(encoding="utf-8")
  self.assertEqual(html.count('id="coverage-30xt"'),1)
  self.assertEqual(html.count('id="coverage-30xt-rows"'),1)
  self.assertEqual(html.count('src="./source_coverage_30xt.js"'),1)
  self.assertIn('id="screen-quality"',html)
 def test_stock_diagnostic_updates_for_navigation_paths(self):
  html=(SITE/"research_hub_30a.html").read_text(encoding="utf-8")
  self.assertIn("if(section==='detail'){renderDetail();renderStockCoverage30U();}",html)
  self.assertIn("function navigateStock(id){",html)
  self.assertIn("display('detail');setQuery({view:'detail',stock:id})",html)
  self.assertIn("renderDetail();renderStockCoverage30U();setQuery(",html)
  self.assertEqual(html.count("function renderStockCoverage30U()"),1)
  self.assertNotIn("addEventListener('click',renderStockCoverage30U)",html)
 def test_fail_closed_renderer(self):
  js=(SITE/"source_coverage_30xt.js").read_text(encoding="utf-8")
  for token in ("response", "prediction_enabled!==false", "certified_trade_samples!==0", "win_rate!==null","replaceChildren","資料目前"):
   if token=="response":continue
   if token=="資料目前":continue
   self.assertIn(token,js)
  self.assertIn("無法核對",js)
  self.assertIn("textContent",js)
if __name__=="__main__":unittest.main()
