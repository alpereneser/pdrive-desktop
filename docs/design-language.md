# Proton-inspired design language

Observed from Proton Drive's public web/login UI and official support material on
2026-08-22. This is an independent client, not an assertion of Proton endorsement.

- GNOME-native three-pane composition: 240 px navigation, flexible content, optional
  details/activity panel.
- Soft lavender canvas (`#f7f5ff`) and white surfaces; dark neutral text.
- Primary purple (`#6d4aff`), purple focus ring, 10–16 px corner radii.
- Left navigation: My files, Computers, Shared, Shared with me, Photos, Trash.
- Main toolbar: breadcrumb, search, list/grid toggle, and a prominent New button.
- File list supports selection toolbar and contextual actions; destructive actions stay
  visually separated and require confirmation.
- Transfer activity remains visible but non-blocking. Empty, loading, offline, and error
  states are designed explicitly.

Native libadwaita widgets and system font metrics take precedence over pixel-perfect web
imitation, preserving accessibility and Zorin/GNOME integration.

