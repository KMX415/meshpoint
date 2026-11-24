/**
 * Micron markup -> DOM, for the Reticulum page's "Browse" (NomadNet) tab.
 *
 * Ported from reticulum-meshchat's src/frontend/js/MicronParser.js
 * (Liam Cottle, MIT), which is itself a port of NomadNet's own
 * MicronParser.py (Mark Qvist, markqvist/NomadNet). Micron format guide:
 * https://github.com/markqvist/NomadNet/blob/master/nomadnet/ui/textui/Guide.py
 *
 * Changes from the meshchat version:
 *  - plain <script> (no ES module) -- exposed as window.MicronParser;
 *  - links: instead of an inline onclick calling a global function, each
 *    <a> gets data-nomad-url / data-nomad-fields and href="nomadnetwork://...";
 *    the Browse tab attaches one delegated click handler.
 * parseToHtml() (used by the Browse tab) builds real DOM nodes via
 * textContent -- no innerHTML, so page content can't inject markup.
 */
class MicronParser {

    constructor(darkTheme = true) {
        this.darkTheme = darkTheme;
        this.DEFAULT_FG_DARK = "ddd";
        this.DEFAULT_FG_LIGHT = "222";
        this.DEFAULT_BG = "default";

        this.STYLES_DARK = {
            "plain":    { fg: this.DEFAULT_FG_DARK, bg: this.DEFAULT_BG, bold: false, underline: false, italic: false },
            "heading1": { fg: "222", bg: "bbb", bold: false, underline: false, italic: false },
            "heading2": { fg: "111", bg: "999", bold: false, underline: false, italic: false },
            "heading3": { fg: "000", bg: "777", bold: false, underline: false, italic: false },
        };
        this.STYLES_LIGHT = {
            "plain":    { fg: this.DEFAULT_FG_LIGHT, bg: this.DEFAULT_BG, bold: false, underline: false, italic: false },
            "heading1": { fg: "000", bg: "777", bold: false, underline: false, italic: false },
            "heading2": { fg: "111", bg: "aaa", bold: false, underline: false, italic: false },
            "heading3": { fg: "222", bg: "ccc", bold: false, underline: false, italic: false },
        };
        this.SELECTED_STYLES = this.darkTheme ? this.STYLES_DARK : this.STYLES_LIGHT;
    }

    static formatNomadnetworkUrl(url) {
        if (/^https?:\/\//i.test(url)) return url;
        if (/^(nomadnetwork|lxmf):\/\//i.test(url)) return url;
        if (/^[a-z][a-z0-9+.-]*:/i.test(url) && !/^[a-f0-9]{32}:\//i.test(url)) return '';
        return `nomadnetwork://${url}`;
    }

    _initialState() {
        return {
            literal: false,
            depth: 0,
            fg_color: this.SELECTED_STYLES.plain.fg,
            bg_color: this.DEFAULT_BG,
            formatting: { bold: false, underline: false, italic: false, strikethrough: false },
            default_align: "left",
            align: "left",
            radio_groups: {},
        };
    }

    parseToHtml(markup) {
        const fragment = document.createDocumentFragment();
        const state = this._initialState();
        for (const line of String(markup).split("\n")) {
            const lineOutput = this.parseLine(line, state);
            if (lineOutput && lineOutput.length > 0) {
                for (const el of lineOutput) fragment.appendChild(el);
            } else {
                fragment.appendChild(document.createElement("br"));
            }
        }
        return fragment;
    }

    parseLine(line, state) {
        if (line.length > 0) {
            if (line === "`=") {
                state.literal = !state.literal;
                return null;
            }

            if (!state.literal) {
                if (line[0] === "#") return null;

                if (line[0] === "<") {
                    state.depth = 0;
                    return this.parseLine(line.slice(1), state);
                }

                if (line[0] === ">") {
                    let i = 0;
                    while (i < line.length && line[i] === ">") i++;
                    state.depth = i;
                    const headingLine = line.slice(i);
                    if (headingLine.length === 0) return null;

                    const wanted = "heading" + i;
                    const style = this.SELECTED_STYLES[wanted] || this.SELECTED_STYLES.plain;
                    const latched = this.stateToStyle(state);
                    this.styleToState(style, state);
                    const outputParts = this.makeOutput(state, headingLine);
                    this.styleToState(latched, state);

                    if (outputParts && outputParts.length > 0) {
                        const div = document.createElement("div");
                        this.applyAlignment(div, state);
                        this.applySectionIndent(div, state);
                        this.appendOutput(div, outputParts, state);
                        return [div];
                    }
                    return null;
                }

                if (line[0] === "-") {
                    const hr = document.createElement("hr");
                    this.applySectionIndent(hr, state);
                    return [hr];
                }
            }

            const outputParts = this.makeOutput(state, line);
            if (outputParts) {
                const container = document.createElement("div");
                this.applyAlignment(container, state);
                this.applySectionIndent(container, state);
                this.appendOutput(container, outputParts, state);
                return [container];
            }
            return [document.createElement("br")];
        }
        return [document.createElement("br")];
    }

    applyAlignment(el, state) {
        el.style.textAlign = state.align || "left";
    }

    applySectionIndent(el, state) {
        const indent = (state.depth - 1) * 2;
        if (indent > 0) el.style.marginLeft = (indent * 10) + "px";
    }

    stateToStyle(state) {
        return {
            fg: state.fg_color,
            bg: state.bg_color,
            bold: state.formatting.bold,
            underline: state.formatting.underline,
            italic: state.formatting.italic,
        };
    }

    styleToState(style, state) {
        if (style.fg != null) state.fg_color = style.fg;
        if (style.bg != null) state.bg_color = style.bg;
        if (style.bold != null) state.formatting.bold = style.bold;
        if (style.underline != null) state.formatting.underline = style.underline;
        if (style.italic != null) state.formatting.italic = style.italic;
    }

    appendOutput(container, parts, state) {
        let currentSpan = null;
        let currentStyle = null;

        const flushSpan = () => {
            if (currentSpan) {
                container.appendChild(currentSpan);
                currentSpan = null;
                currentStyle = null;
            }
        };

        for (const p of parts) {
            if (typeof p === "string") {
                const span = document.createElement("span");
                span.textContent = p;
                container.appendChild(span);
            } else if (Array.isArray(p) && p.length === 2) {
                const [styleSpec, text] = p;
                if (!this.stylesEqual(styleSpec, currentStyle)) {
                    flushSpan();
                    currentSpan = document.createElement("span");
                    this.applyStyleToElement(currentSpan, styleSpec);
                    currentStyle = styleSpec;
                }
                currentSpan.textContent += text;
            } else if (p && typeof p === "object") {
                flushSpan();
                if (p.type === "field") {
                    const input = document.createElement("input");
                    input.type = p.masked ? "password" : "text";
                    input.name = p.name;
                    input.setAttribute("value", p.data);
                    if (p.width) input.size = p.width;
                    this.applyStyleToElement(input, p.style);
                    container.appendChild(input);
                } else if (p.type === "checkbox" || p.type === "radio") {
                    const label = document.createElement("label");
                    const box = document.createElement("input");
                    box.type = p.type;
                    box.name = p.name;
                    box.value = p.value;
                    if (p.prechecked) box.setAttribute("checked", "true");
                    label.appendChild(box);
                    label.appendChild(document.createTextNode(" " + p.label));
                    this.applyStyleToElement(label, p.style);
                    container.appendChild(label);
                } else if (p.type === "link") {
                    container.appendChild(this._buildLink(p));
                }
            }
        }
        flushSpan();
    }

    /** A Micron link -> an <a> the Browse tab intercepts. `data-nomad-url`
     * is the `<hash>:/path` (optionally with `\`var=val|...`); the href is
     * the display-only `nomadnetwork://...` form. */
    _buildLink(p) {
        if (!p.url) {
            const span = document.createElement('span');
            span.textContent = p.label;
            return span;
        }
        if (/^https?:\/\//i.test(p.url)) {
            const external = document.createElement('a');
            external.href = p.url;
            external.textContent = p.label;
            external.target = '_blank';
            external.rel = 'noopener noreferrer';
            return external;
        }
        let directURL = p.url.replace("nomadnetwork://", "").replace("lxmf://", "");
        const a = document.createElement("a");
        a.href = p.url;
        a.title = p.url;
        a.textContent = p.label;

        const fieldsToSubmit = [];
        const requestVars = {};
        let submitAll = false;

        for (const f of (p.fields || [])) {
            if (f === "*") submitAll = true;
            else if (f.includes("=")) {
                const [k, v] = f.split("=");
                requestVars[k] = v;
            } else {
                fieldsToSubmit.push(f);
            }
        }

        const varEntries = Object.entries(requestVars);
        if (varEntries.length > 0) {
            const qs = varEntries.map(([k, v]) => `${k}=${v}`).join("|");
            directURL += directURL.includes("`") ? `|${qs}` : `\`${qs}`;
        }

        a.dataset.nomadUrl = directURL;
        if (submitAll) a.dataset.nomadFields = "*";
        else if (fieldsToSubmit.length > 0) a.dataset.nomadFields = fieldsToSubmit.join("|");

        this.applyStyleToElement(a, p.style);
        return a;
    }

    stylesEqual(s1, s2) {
        if (!s1 && !s2) return true;
        if (!s1 || !s2) return false;
        return s1.fg === s2.fg && s1.bg === s2.bg && s1.bold === s2.bold
            && s1.underline === s2.underline && s1.italic === s2.italic;
    }

    applyStyleToElement(el, style) {
        if (!style) return;
        const fg = this.colorToCss(style.fg);
        const bg = this.colorToCss(style.bg);
        if (fg && fg !== "default") el.style.color = fg;
        if (bg && bg !== "default") el.style.backgroundColor = bg;
        if (style.bold) el.style.fontWeight = "bold";
        if (style.underline) {
            el.style.textDecoration = el.style.textDecoration
                ? el.style.textDecoration + " underline" : "underline";
        }
        if (style.italic) el.style.fontStyle = "italic";
    }

    colorToCss(c) {
        if (!c || c === "default") return null;
        if (c.length === 3 && /^[0-9a-fA-F]{3}$/.test(c)) return "#" + c;
        if (c.length === 6 && /^[0-9a-fA-F]{6}$/.test(c)) return "#" + c;
        if (c.length === 3 && c[0] === "g") {
            let val = parseInt(c.slice(1), 10);
            if (isNaN(val)) val = 50;
            const h = Math.floor(val * 2.55).toString(16).padStart(2, "0");
            return "#" + h + h + h;
        }
        return null;
    }

    makeOutput(state, line) {
        if (state.literal) {
            if (line === "\\`=") line = "`=";
            return [[this.stateToStyle(state), line]];
        }

        const output = [];
        let part = "";
        let mode = "text";
        let escape = false;
        let skip = 0;
        let i = 0;

        while (i < line.length) {
            const c = line[i];
            if (skip > 0) { skip--; i++; continue; }

            if (mode === "formatting") {
                switch (c) {
                    case "_": state.formatting.underline = !state.formatting.underline; break;
                    case "!": state.formatting.bold = !state.formatting.bold; break;
                    case "*": state.formatting.italic = !state.formatting.italic; break;
                    case "F":
                        if (line.length >= i + 4) { state.fg_color = line.substr(i + 1, 3); skip = 3; }
                        break;
                    case "f": state.fg_color = this.SELECTED_STYLES.plain.fg; break;
                    case "B":
                        if (line.length >= i + 4) { state.bg_color = line.substr(i + 1, 3); skip = 3; }
                        break;
                    case "b": state.bg_color = this.DEFAULT_BG; break;
                    case "`":
                        state.formatting.bold = false;
                        state.formatting.underline = false;
                        state.formatting.italic = false;
                        state.fg_color = this.SELECTED_STYLES.plain.fg;
                        state.bg_color = this.DEFAULT_BG;
                        state.align = state.default_align;
                        break;
                    case "c": state.align = (state.align === "center") ? state.default_align : "center"; break;
                    case "l": state.align = (state.align === "left") ? state.default_align : "left"; break;
                    case "r": state.align = (state.align === "right") ? state.default_align : "right"; break;
                    case "a": state.align = state.default_align; break;
                    case "<": {
                        if (part.length > 0) { output.push([this.stateToStyle(state), part]); part = ""; }
                        const fieldData = this.parseField(line, i, state);
                        if (fieldData) { output.push(fieldData.obj); i += fieldData.skip; mode = "text"; continue; }
                        break;
                    }
                    case "[": {
                        if (part.length > 0) { output.push([this.stateToStyle(state), part]); part = ""; }
                        const linkData = this.parseLink(line, i, state);
                        if (linkData) { output.push(linkData.obj); i += linkData.skip; mode = "text"; continue; }
                        break;
                    }
                    default: break;
                }
                mode = "text";
            } else {
                if (c === "\\") {
                    if (escape) { part += c; escape = false; }
                    else escape = true;
                } else if (c === "`") {
                    if (escape) { part += c; escape = false; }
                    else {
                        if (part.length > 0) { output.push([this.stateToStyle(state), part]); part = ""; }
                        mode = "formatting";
                    }
                } else {
                    if (escape) { part += "\\"; escape = false; }
                    part += c;
                }
            }
            i++;
        }

        if (part.length > 0) output.push([this.stateToStyle(state), part]);
        return output.length > 0 ? output : null;
    }

    parseField(line, startIndex, state) {
        const field_start = startIndex + 1;
        const backtick_pos = line.indexOf("`", field_start);
        if (backtick_pos === -1) return null;

        const field_content = line.substring(field_start, backtick_pos);
        let field_masked = false;
        let field_width = 24;
        let field_type = "field";
        let field_name = field_content;
        let field_value = "";
        let field_prechecked = false;

        if (field_content.includes("|")) {
            const f = field_content.split("|");
            let flags = f[0];
            field_name = f[1];
            if (flags.includes("^")) { field_type = "radio"; flags = flags.replace("^", ""); }
            else if (flags.includes("?")) { field_type = "checkbox"; flags = flags.replace("?", ""); }
            else if (flags.includes("!")) { field_masked = true; flags = flags.replace("!", ""); }
            if (flags.length > 0) {
                const w = parseInt(flags, 10);
                if (!isNaN(w)) field_width = Math.min(w, 256);
            }
            if (f.length > 2) field_value = f[2];
            if (f.length > 3 && f[3] === "*") field_prechecked = true;
        }

        const field_end = line.indexOf(">", backtick_pos);
        if (field_end === -1) return null;

        const field_data = line.substring(backtick_pos + 1, field_end);
        const style = this.stateToStyle(state);

        let obj;
        if (field_type === "checkbox" || field_type === "radio") {
            obj = {
                type: field_type, name: field_name,
                value: field_value || field_data, label: field_data,
                prechecked: field_prechecked, style,
            };
        } else {
            obj = {
                type: "field", name: field_name, width: field_width,
                masked: field_masked, data: field_data, style,
            };
        }
        return { obj, skip: (field_end - startIndex) + 2 };
    }

    parseLink(line, startIndex, state) {
        const endpos = line.indexOf("]", startIndex);
        if (endpos === -1) return null;

        const link_data = line.substring(startIndex + 1, endpos);
        const parts = link_data.split("`");
        let label = "";
        let url = "";
        let fields = "";
        if (parts.length === 1) { url = link_data; }
        else if (parts.length === 2) { label = parts[0]; url = parts[1]; }
        else if (parts.length === 3) { label = parts[0]; url = parts[1]; fields = parts[2]; }

        if (url.length === 0) return null;
        if (label === "") label = url;

        const obj = {
            type: "link",
            url: MicronParser.formatNomadnetworkUrl(url),
            label,
            fields: fields ? fields.split("|") : [],
            style: this.stateToStyle(state),
        };
        return { obj, skip: (endpos - startIndex) + 2 };
    }
}

window.MicronParser = MicronParser;
