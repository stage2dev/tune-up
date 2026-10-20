---
name: {{project_name}}
description: {{one_line_visual_identity}}
colors:
  primary: "{{hex}}"
  secondary: "{{hex}}"
  surface: "{{hex}}"
  text: "{{hex}}"
  error: "{{hex}}"
typography:
  body:
    fontFamily: "{{font}}"
    fontSize: "{{size}}"
    fontWeight: {{weight}}
    lineHeight: "{{line_height}}"
  heading:
    fontFamily: "{{font}}"
    fontSize: "{{size}}"
    fontWeight: {{weight}}
rounded:
  md: "{{radius}}"
spacing:
  sm: "{{space}}"
  md: "{{space}}"
  lg: "{{space}}"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
---

# {{project_name}} - {{names.design}}

## Overview
{{brand_and_style}}

## Colors
{{how_each_color_is_used}}

## Typography
{{type_rules}}

## Layout and spacing
{{grid_and_rhythm}}

## Elevation and depth
{{shadows_layers}}

## Shapes
{{corners_borders}}

## Components
{{component_notes}}

## Do and don't
- Do: {{rule}}
- Don't: {{rule}}

## Voice and tone
| Do | Don't |
|---|---|
| {{example}} | {{counter_example}} |

## Key flows
- {{persona}} at {{moment}}: {{steps}}
