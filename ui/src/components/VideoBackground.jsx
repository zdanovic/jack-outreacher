import React from "react";

export default function VideoBackground({ opacity = 0.45 }) {
  return (
    <div className="bg-video-wrap" aria-hidden="true">
      <div className="bg-static" />
      <div className="bg-video-overlay" style={{ opacity }} />
    </div>
  );
}
