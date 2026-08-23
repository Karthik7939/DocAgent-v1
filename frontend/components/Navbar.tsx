"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";

export default function Navbar() {
  const pathname = usePathname();

  const navItems = [
    {
      name: "Dashboard",
      href: "/",
      icon: (
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      ),
    },
    // {
    //   name: "Repositories",
    //   href: "/repos",
    //   icon: (
    //     <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    //       <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
    //     </svg>
    //   ),
    // },
    {
      name: "Documentation",
      href: "/review",
      icon: (
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    },
    {
      name: "GitBook",
      href: "/gitbook",
      icon: (
        <svg className="w-3.5 h-3.5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
      ),
    },
    {
      name: "Knowledge Base",
      href: "/knowledge-base",
      icon: (
        <svg className="w-3.5 h-3.5 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8-4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
        </svg>
      ),
    },
    {
      name: "Debugging",
      href: "/debug",
      icon: (
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
      ),
    },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-surface/85 backdrop-blur-xl shadow-xs transition-all">
      <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-4 sm:px-6">
        
        {/* Brand Logo & Title */}
        <Link
          href="/"
          className="group flex items-center gap-3 font-bold tracking-tight text-text transition-all"
        >
          {/* Custom 3D Logo Icon */}
          <div className="relative flex h-10 w-10 flex-shrink-0 items-center justify-center transition-transform duration-300 group-hover:scale-105">
            <Image
              src="/logo.png"
              alt="DocAgent Logo"
              width={40}
              height={40}
              className="h-10 w-10 object-contain rounded-xl drop-shadow-xs"
              priority
            />
          </div>

          <div className="flex flex-col justify-center">
            <div className="flex items-center gap-2 leading-none">
              <span className="text-base font-extrabold tracking-tight text-text font-sans">
                Doc<span className="text-accent">Agent</span>
              </span>
            </div>
            <span className="text-[10px] font-bold tracking-wider uppercase text-muted/90 mt-1">
              Autonomous Doc Engine
            </span>
          </div>
        </Link>



        {/* Navigation Items in Floating Container */}
        <nav className="flex items-center gap-1 rounded-2xl border border-border/50 bg-canvas/70 p-1 shadow-inner backdrop-blur-md">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all duration-200 ${
                  isActive
                    ? "bg-white text-accent shadow-xs border border-amber-900/10 font-bold"
                    : "text-muted hover:bg-white/50 hover:text-text"
                }`}
              >
                <span className={isActive ? "text-accent" : "opacity-70 group-hover:opacity-100"}>
                  {item.icon}
                </span>
                <span>{item.name}</span>
                {isActive && (
                  <span className="absolute bottom-0 left-3 right-3 h-0.5 rounded-full bg-accent" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Status Pill Badge */}
        <div className="hidden md:flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-800">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <span>Agent Active</span>
          </div>
        </div>

      </div>
    </header>
  );
}

