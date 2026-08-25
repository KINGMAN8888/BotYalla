"""مجموعة أيقونات BotYalla — خطية مخصّصة (inline SVG)، تأخذ اللون الحالي (currentColor).
الاستخدام في القوالب: {{ icon('bots') }} أو {{ icon('store', 20) }}."""
from markupsafe import Markup

# كل أيقونة: مسارات SVG بحجم 24×24، stroke=currentColor
_P = {
 "grid":       '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
 "bot":        '<rect x="4" y="8" width="16" height="11" rx="3"/><path d="M12 8V4"/><circle cx="12" cy="3" r="1.2"/><circle cx="9" cy="13" r="1.2"/><circle cx="15" cy="13" r="1.2"/><path d="M9.5 16.5h5"/><path d="M2 12v3M22 12v3"/>',
 "store":      '<path d="M4 9h16l-1 11H5L4 9z"/><path d="M4 9l1.2-4.2A2 2 0 0 1 7.1 3.4h9.8a2 2 0 0 1 1.9 1.4L20 9"/><path d="M9 13a3 3 0 0 0 6 0"/>',
 "calendar":   '<rect x="3" y="5" width="18" height="16" rx="2.5"/><path d="M3 10h18M8 3v4M16 3v4"/><circle cx="8.5" cy="14.5" r="1.1"/><circle cx="12" cy="14.5" r="1.1"/><circle cx="15.5" cy="14.5" r="1.1"/>',
 "flow":       '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="12" r="2.5"/><circle cx="6" cy="18" r="2.5"/><path d="M8.3 7.2 15.7 10.8M8.2 16.9 15.6 13.2"/>',
 "megaphone":  '<path d="M4 10v4a1 1 0 0 0 1 1h2l7 4V5L7 9H5a1 1 0 0 0-1 1z"/><path d="M17 8a5 5 0 0 1 0 8"/><path d="M7 15v3a1.5 1.5 0 0 0 3 0v-2"/>',
 "chart":      '<path d="M4 20V4"/><path d="M4 20h16"/><rect x="7" y="12" width="3" height="5" rx="1"/><rect x="12" y="8" width="3" height="9" rx="1"/><rect x="17" y="5" width="3" height="12" rx="1"/>',
 "settings":   '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.2A1.6 1.6 0 0 0 7 19.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H3a2 2 0 1 1 0-4h.2A1.6 1.6 0 0 0 4.7 7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9.5A1.6 1.6 0 0 0 10.6 3V3a2 2 0 1 1 4 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9.5a1.6 1.6 0 0 0 1.5 1.1H21a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.4.9z"/>',
 "key":        '<circle cx="8" cy="15" r="4"/><path d="M10.8 12.2 20 3M17 6l2 2M14 9l2 2"/>',
 "link":       '<path d="M9.5 13.5 14.5 8.5"/><path d="M8 10 5.8 12.2a3.5 3.5 0 0 0 5 5L13 15"/><path d="M16 14l2.2-2.2a3.5 3.5 0 0 0-5-5L11 9"/>',
 "play":       '<path d="M7 5.5v13a1 1 0 0 0 1.5.87l11-6.5a1 1 0 0 0 0-1.74l-11-6.5A1 1 0 0 0 7 5.5z"/>',
 "stop":       '<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
 "trash":      '<path d="M4 7h16M9 7V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2M6 7l1 13a1.5 1.5 0 0 0 1.5 1.4h7A1.5 1.5 0 0 0 17 20L18 7"/><path d="M10 11v6M14 11v6"/>',
 "plus":       '<path d="M12 5v14M5 12h14"/>',
 "check":      '<path d="M4 12.5 9.5 18 20 6.5"/>',
 "sparkles":   '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6L12 3z"/><path d="M18.5 14l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7.7-1.9z"/>',
 "image":      '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="8.5" cy="9.5" r="1.8"/><path d="M4.5 18l4.5-4.5a2 2 0 0 1 2.8 0L20 21.5"/>',
 "wallet":     '<rect x="3" y="6" width="18" height="13" rx="2.5"/><path d="M3 9h18"/><path d="M16 13.5h2.5"/><path d="M3 6l2-2.2A2 2 0 0 1 6.5 3H16a2 2 0 0 1 2 2v1"/>',
 "users":      '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><path d="M16 5.2a3.2 3.2 0 0 1 0 6.1M17.5 20a5.5 5.5 0 0 0-2.3-4.5"/>',
 "inbox":      '<path d="M4 13l2.5-8A2 2 0 0 1 8.4 3.6h7.2A2 2 0 0 1 17.5 5L20 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-5z"/><path d="M4 13h4a2 2 0 0 1 2 2 2 2 0 0 0 4 0 2 2 0 0 1 2-2h4"/>',
 "logout":     '<path d="M14 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 8l-4 4 4 4M6 12h9"/>',
 "globe":      '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.4 4 5.5 4 9s-1.4 6.6-4 9c-2.6-2.4-4-5.5-4-9s1.4-6.6 4-9z"/>',
 "back":       '<path d="M14 7l-5 5 5 5"/>',
 "download":   '<path d="M12 4v10M8 11l4 3 4-3"/><path d="M5 18h14"/>',
 "bolt":       '<path d="M13 3 5 13h5l-1 8 8-10h-5l1-8z"/>',
 "phone":      '<path d="M6 3h3l1.6 4-2 1.4a12 12 0 0 0 5 5l1.4-2 4 1.6V21a1 1 0 0 1-1 1A17 17 0 0 1 5 4a1 1 0 0 1 1-1z"/>',
 "shield":     '<path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
 "crown":      '<path d="M4 8l3 3 3-5 2 5 2-5 3 5 3-3-1.5 11H5.5L4 8z"/>',
 "tag":        '<path d="M4 4h7l9 9-7 7-9-9V4z"/><circle cx="8" cy="8" r="1.4"/>',
 "rocket":     '<path d="M12 3c3 1 5 4 5 8l-2 4H9l-2-4c0-4 2-7 5-8z"/><circle cx="12" cy="9" r="1.5"/><path d="M9 15l-2 4M15 15l2 4M12 15v5"/>',
 "upload": '<path d="M12 16V6M8 9l4-3 4 3"/><path d="M5 18h14"/>',
 "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 "ban": '<circle cx="12" cy="12" r="9"/><path d="M6 6l12 12"/>',
 "card": '<rect x="3" y="6" width="18" height="12" rx="2.5"/><path d="M3 10h18"/><path d="M7 15h4"/>',
 "bank": '<path d="M4 10h16M5 10 12 4l7 6M6 10v7M10 10v7M14 10v7M18 10v7M4 20h16"/>',
 "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
}

def icon(name, size=18, cls=""):
    body = _P.get(name)
    if not body:
        body = _P["grid"]
    return Markup(
        f'<svg class="ic {cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{body}</svg>')
