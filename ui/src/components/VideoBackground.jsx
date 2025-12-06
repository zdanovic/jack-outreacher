import React, { useMemo } from "react";

export default function VideoBackground({
  sources = [
    { src: "/media/bg.webm?v=6", type: "video/webm" },
    { src: "/media/bg.mp4?v=6", type: "video/mp4" },
  ],
  poster = "/media/bg-poster.jpg",
  opacity = 0.35,
  saturate = 1.2,
  brightness = 0.85,
}) {
  const prefersReducedMotion = useMemo(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  }, []);

  return (
    <div className="bg-video-wrap" aria-hidden="true">
      {prefersReducedMotion ? (
        <img
          className="bg-video bg-poster"
          src={poster}
          alt=""
          loading="lazy"
          decoding="async"
          style={{ filter: `saturate(${saturate}) brightness(${brightness})` }}
        />
      ) : (
        <video
          className="bg-video"
          autoPlay
          loop
          muted
          playsInline
          poster={poster || undefined}
          preload="metadata"
          style={{ filter: `saturate(${saturate}) brightness(${brightness})` }}
        >
          {sources.map((s) => (
            <source key={s.src} src={s.src} type={s.type} />
          ))}
        </video>
      )}
      <div className="bg-video-overlay" style={{ opacity }} />
    </div>
  );
}
