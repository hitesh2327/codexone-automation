import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Minus, Move, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const PREVIEW = 288;      // on-screen square
const OUTPUT = 384;       // exported square (px)
const MAX_BYTES = 380 * 1024; // server limit is 400 KB

type Point = { x: number; y: number };

/** Drag to position, slide to zoom; saves a square JPEG (the server only ever stores that). */
export function AvatarCropper({
  file, onCancel, onSave,
}: { file: File | null; onCancel: () => void; onSave: (blob: Blob) => Promise<void> }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState<Point>({ x: 0, y: 0 });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const drag = useRef<{ start: Point; origin: Point } | null>(null);

  // load the chosen file
  useEffect(() => {
    setImg(null); setError(null); setZoom(1); setOffset({ x: 0, y: 0 });
    if (!file) return;
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => setImg(im);
    im.onerror = () => setError("That file couldn't be read as a picture.");
    im.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  /** Size the image is drawn at for a square of `side` px, at the current zoom ("cover" fit). */
  const drawSize = useCallback((side: number) => {
    if (!img) return { w: 0, h: 0 };
    const base = Math.max(side / img.naturalWidth, side / img.naturalHeight);
    return { w: img.naturalWidth * base * zoom, h: img.naturalHeight * base * zoom };
  }, [img, zoom]);

  const clamp = useCallback((o: Point, side: number): Point => {
    const { w, h } = drawSize(side);
    const mx = Math.max(0, (w - side) / 2), my = Math.max(0, (h - side) / 2);
    return { x: Math.min(mx, Math.max(-mx, o.x)), y: Math.min(my, Math.max(-my, o.y)) };
  }, [drawSize]);

  const paint = useCallback((ctx: CanvasRenderingContext2D, side: number, o: Point) => {
    if (!img) return;
    const { w, h } = drawSize(side);
    ctx.fillStyle = "#0D1117";
    ctx.fillRect(0, 0, side, side);
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(img, (side - w) / 2 + o.x, (side - h) / 2 + o.y, w, h);
  }, [img, drawSize]);

  useEffect(() => {
    const c = canvas.current;
    const ctx = c?.getContext("2d");
    if (!c || !ctx) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = c.height = PREVIEW * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    paint(ctx, PREVIEW, clamp(offset, PREVIEW));
  }, [img, zoom, offset, paint, clamp]);

  // keep the image covering the frame when zoom shrinks
  useEffect(() => setOffset((o) => clamp(o, PREVIEW)), [zoom, clamp]);

  function onPointerDown(e: React.PointerEvent) {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { start: { x: e.clientX, y: e.clientY }, origin: offset };
  }
  function onPointerMove(e: React.PointerEvent) {
    if (!drag.current) return;
    const { start, origin } = drag.current;
    setOffset(clamp({ x: origin.x + e.clientX - start.x, y: origin.y + e.clientY - start.y }, PREVIEW));
  }
  function onKey(e: React.KeyboardEvent) {
    const step = e.shiftKey ? 24 : 8;
    const d: Record<string, Point> = { ArrowLeft: { x: step, y: 0 }, ArrowRight: { x: -step, y: 0 }, ArrowUp: { x: 0, y: step }, ArrowDown: { x: 0, y: -step } };
    if (d[e.key]) { e.preventDefault(); setOffset((o) => clamp({ x: o.x + d[e.key].x, y: o.y + d[e.key].y }, PREVIEW)); }
    if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(3, +(z + 0.1).toFixed(2)));
    if (e.key === "-") setZoom((z) => Math.max(1, +(z - 0.1).toFixed(2)));
  }

  async function save() {
    if (!img) return;
    setSaving(true);
    setError(null);
    try {
      const out = document.createElement("canvas");
      out.width = out.height = OUTPUT;
      const ctx = out.getContext("2d")!;
      const scale = OUTPUT / PREVIEW;
      paint(ctx, OUTPUT, { x: clamp(offset, PREVIEW).x * scale, y: clamp(offset, PREVIEW).y * scale });
      let blob: Blob | null = null;
      for (const q of [0.9, 0.82, 0.72, 0.6, 0.5]) {
        blob = await new Promise<Blob | null>((res) => out.toBlob(res, "image/jpeg", q));
        if (blob && blob.size <= MAX_BYTES) break;
      }
      if (!blob || blob.size > MAX_BYTES) throw new Error("This picture is too detailed to shrink enough. Try another one.");
      await onSave(blob);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the picture.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={!!file} onOpenChange={(o) => { if (!o && !saving) onCancel(); }}>
      <DialogContent className="max-w-[26rem] gap-5">
        <DialogHeader>
          <DialogTitle className="font-heading">Frame your picture</DialogTitle>
          <DialogDescription>Drag to move it, slide to zoom. We save a square copy; the original stays on your device.</DialogDescription>
        </DialogHeader>

        <div className="grid justify-center">
          <div
            className="relative touch-none select-none rounded-[30%] outline-none ring-offset-2 ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
            style={{ width: PREVIEW, height: PREVIEW }}
            tabIndex={0}
            role="img"
            aria-label="Picture preview. Use arrow keys to move, plus and minus to zoom."
            onKeyDown={onKey}
          >
            <canvas
              ref={canvas}
              style={{ width: PREVIEW, height: PREVIEW }}
              className={`rounded-[30%] bg-muted ${img ? "cursor-grab active:cursor-grabbing" : ""}`}
              onPointerDown={onPointerDown} onPointerMove={onPointerMove}
              onPointerUp={() => (drag.current = null)} onPointerCancel={() => (drag.current = null)}
            />
            {/* the part that will be cut away fades; the frame's shape is the avatar's shape */}
            <span aria-hidden className="pointer-events-none absolute inset-0 rounded-[30%] ring-1 ring-white/25" />
            {!img && !error && <span className="absolute inset-0 grid place-items-center text-sm text-muted-foreground"><LoaderCircle className="animate-spin" /></span>}
            {img && <Move aria-hidden className="pointer-events-none absolute right-3 bottom-3 size-4 text-white/60" />}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button type="button" variant="ghost" size="icon" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(1, +(z - 0.1).toFixed(2)))}><Minus /></Button>
          <input
            type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))}
            aria-label="Zoom" className="h-1.5 flex-1 cursor-pointer accent-[var(--brand-accent)]" disabled={!img}
          />
          <Button type="button" variant="ghost" size="icon" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(3, +(z + 0.1).toFixed(2)))}><Plus /></Button>
        </div>

        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={onCancel} disabled={saving}>Cancel</Button>
          <Button onClick={save} disabled={!img || saving}>
            {saving && <LoaderCircle className="animate-spin" />}
            {saving ? "Saving…" : "Use this picture"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
