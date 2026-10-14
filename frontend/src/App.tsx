import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Workbench from "./pages/Workbench";
import Products from "./pages/Products";
import ListingGen from "./pages/ListingGen";
import SeoStudio from "./pages/SeoStudio";
import ImageStudio from "./pages/ImageStudio";
import ListingEditor from "./pages/ListingEditor";
import ReviewCenter from "./pages/ReviewCenter";
import BatchTasks from "./pages/BatchTasks";
import ExportCenter from "./pages/ExportCenter";
import ModelSettings from "./pages/ModelSettings";
import RulesCenter from "./pages/RulesCenter";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Workbench />} />
        <Route path="/products" element={<Products />} />
        <Route path="/listings" element={<ListingGen />} />
        <Route path="/seo" element={<SeoStudio />} />
        <Route path="/images" element={<ImageStudio />} />
        <Route path="/editor" element={<ListingEditor />} />
        <Route path="/reviews" element={<ReviewCenter />} />
        <Route path="/tasks" element={<BatchTasks />} />
        <Route path="/exports" element={<ExportCenter />} />
        <Route path="/settings" element={<ModelSettings />} />
        <Route path="/rules" element={<RulesCenter />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
