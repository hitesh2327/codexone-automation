import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { RequireAuth } from "@/lib/auth";
import { applyBrand, type Brand } from "@/lib/brand";
import Login from "@/pages/Login";
import Signup from "@/pages/Signup";
import Generate from "@/pages/Generate";
import Logs from "@/pages/Logs";
import Posts from "@/pages/Posts";
import Profile from "@/pages/Profile";
import Recover from "@/pages/Recover";
import Subscription from "@/pages/Subscription";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Config = lazy(() => import("@/pages/Config"));
const ConfigGuide = lazy(() => import("@/pages/ConfigGuide"));

export default function App() {
  const [brand, setBrand] = useState<Brand | null>(null);

  useEffect(() => {
    applyBrand().then(setBrand);
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<Login brand={brand} />} />
      <Route path="/signup" element={<Signup brand={brand} />} />
      <Route path="/forgot-password" element={<Recover brand={brand} />} />
      <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
      <Route path="/subscription" element={<RequireAuth><Subscription /></RequireAuth>} />
      <Route path="/dashboard" element={<RequireAuth><Suspense fallback={null}><Dashboard /></Suspense></RequireAuth>} />
      <Route path="/posts" element={<RequireAuth><Posts /></RequireAuth>} />
      <Route path="/generate" element={<RequireAuth><Generate /></RequireAuth>} />
      <Route path="/logs" element={<RequireAuth><Logs /></RequireAuth>} />
      <Route path="/config" element={<RequireAuth><Suspense fallback={null}><Config /></Suspense></RequireAuth>} />
      <Route path="/config/guide/:topic?" element={<RequireAuth><Suspense fallback={null}><ConfigGuide /></Suspense></RequireAuth>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
