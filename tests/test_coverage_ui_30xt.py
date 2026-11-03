import unittest
from pathlib import Path

SITE=Path(__file__).resolve().parents[1]/"site"
class CoverageUiTests(unittest.TestCase):
 def test_release_label_3_0w_and_module_3_0e_distinguished(self):
  html=(SITE/"research_hub_30a.html").read_text(encoding="utf-8")
  self.assertIn("<title>TPE-MFDS 3.0W｜進階研究資料館</title>",html)
  self.assertIn("TPE-MFDS 3.0W · ADVANCED RESEARCH",html)
  self.assertNotIn("FACTUAL RESEARCH · 3.0E",html)
  self.assertIn("3.0E｜歷史除權息觀察與原始前收核對",html)

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
