/* An SVG renderer for DELPH-IN derivation trees. Targets the ERG API that is
 * currently under development and is documented here:
 * http://moin.delph-in.net/ErgApi
 *
 * This code is adapted from code found in Woodley Packard's full forest treebanker,
 * which can be found here: http://sweaglesw.org/svn/treebank/trunk/
 *
 * Usage:
 *     drawTree(derivation, element)
 *
 * Where 'derivation' is a derivation object as found in the ERG API, and
 * 'element' as an element for the resultant SVG element to be appended to the
 * end of its content.
 */


// Horizontal distance between nodes
const DAUGHTER_HSPACE = 20;

// Vertical distance between nodes
const DAUGHTER_VSPACE = 30;


function drawTree(element, derivation) {
    // need to add the SVG to the DOM before rendering, otherwise the height of
    // SVG elements won't be available during rendering.
    const svg = svgelement('svg');
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svg.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    svg.setAttribute("version", "1.1");
    element.appendChild(svg);

    const g = render_tree(svg, derivation);
    svg.appendChild(g);

    // Set dimensions on the SVG element from its top level g element
    const bbox = g.getBBox();
    svg.setAttribute("height", bbox.height);
    svg.setAttribute("width", bbox.width);

    return svg;
}


function render_tree(svg, tree) {
    let lexical;
    const daughters = [];
    let wtot = -DAUGHTER_HSPACE;
    let dtr_label_mean = 0;
    const daughterNodes = tree.daughters || [];

    for (let i = 0; i < daughterNodes.length; i++) {
        wtot += DAUGHTER_HSPACE;
        daughters[i] = render_tree(svg, daughterNodes[i]);
        dtr_label_mean += wtot + daughters[i].labelcenter;
        wtot += daughters[i].mywidth;
    }

    if (daughters.length) {
        dtr_label_mean /= daughters.length;
    } else {
        lexical = render_yield(svg, tree.form);
        wtot = lexical.mywidth;
        dtr_label_mean = wtot / 2;
    }

    const node_str = tree.hasOwnProperty("label") ? tree.label : tree.entity;

    const g = svgelement("g");
    const n = text(svg, node_str);
    n.setAttribute("title", tree.entity);
    n.classList.add("ltdb");

    // add a title element for node tooltips
    const title = svgelement('title');
    title.innerHTML = tree.entity;
    n.appendChild(title);

    g.appendChild(n);

    const daughters_wtot = wtot;
    const nw = n.bbx.width;
    const nh = n.bbx.height;
    let labelcenter = dtr_label_mean;

    if (labelcenter - nw/2 < 0)
        labelcenter = nw/2;

    if (labelcenter + nw/2 > wtot)
        labelcenter = wtot - nw/2;

    if (nw > wtot) {
        wtot = nw;
        labelcenter = wtot / 2;
    }

    n.setAttribute("x", labelcenter - nw / 2);
    n.setAttribute("y", nh * 2/3);

    let dtr_x = wtot / 2 - daughters_wtot / 2;
    const ytrans = nh + DAUGHTER_VSPACE;

    if (lexical) {
        lexical.setAttribute("transform", "translate(" + dtr_x + "," + ytrans + ")");
        lexical.setAttribute("class", "leaf");
        g.appendChild(line(labelcenter, nh, wtot/2, nh + DAUGHTER_VSPACE - 1));
        g.appendChild(lexical);
    } else {
        for (let i = 0; i < daughters.length; i++) {
            const daughter = daughters[i];
            daughter.setAttribute("transform", "translate(" + dtr_x + "," + ytrans + ")");
            g.appendChild(line(labelcenter, nh, dtr_x + daughter.labelcenter, nh + DAUGHTER_VSPACE - 1));
            g.appendChild(daughter);
            dtr_x += daughter.mywidth + DAUGHTER_HSPACE;
        }
    }

    g.mywidth = wtot;
    g.labelcenter = labelcenter;
    g.labelheight = nh;
    return g;
}


function render_yield(svg, str) {
    const y = text(svg, str);
    y.setAttribute("y", y.bbx.height * 2/3);
    const g = svgelement("g");
    g.appendChild(y);
    g.mywidth = y.bbx.width;
    return g;
}


function svgelement(type) {
    return document.createElementNS("http://www.w3.org/2000/svg", type);
}


function line(x1, y1, x2, y2) {
    const l = svgelement("line");
    l.setAttribute("x1", x1);
    l.setAttribute("x2", x2);
    l.setAttribute("y1", y1);
    l.setAttribute("y2", y2);
    l.setAttribute("style", "stroke: black;");
    return l;
}


function text(svg, str) {
    const t = svgelement("text");
    t.appendChild(document.createTextNode(str));
    svg.appendChild(t);
    const bbx = t.getBBox();
    svg.removeChild(t);
    t.bbx = bbx;
    return t;
}
