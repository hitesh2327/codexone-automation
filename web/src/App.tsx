import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "@/lib/auth";
import { applyBrand, type Brand } from "@/lib/brand";
import Home from "@/pages/Home";
import Login from "@/pages/Login";

export default function App() {
  const [brand, setBrand] = useState<Brand | null>(null);

  useEffect(() => {
    applyBrand().then(setBrand);
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<Login brand={brand} />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Home />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
