#!/usr/bin/python3
from string import Template
import lxml.html
from lxml import etree
import copy
import re
import os
import sass

VERSION = "0.1"

variable_pattern = re.compile("\{\{\{([^}]+)\}\}\}")

def dom2str(element):
    return lxml.html.tostring(element, encoding=str)
def dom2innerstr(element):
    text = lxml.html.tostring(element, encoding=str)
    return text[text.find(">")+1:text.rfind("<")]
def replace(text, rule, replacer):
    matches = [(match.start(), match.end(), match.groups()[0].strip()) for match in re.finditer(rule, text)]
    matches.reverse()
    characters = list(text)
    for start, end, variable in matches:
        characters[start:end] = replacer(variable)
    return "".join(characters) 

def compile(path, variables={}, innerhtmls=[], isroot=True, statics={}):
    # 1. build tree
    with open(path) as f:
        text = f.read()
        # 1.1. replace variable
        replace(text, variable_pattern, lambda x: variables[x])
        if text.strip().startswith("<!DOCTYPE") or text.strip().startswith("<html"):  
            roots = (lxml.html.fromstring(text),)
        else:
            roots = lxml.html.fragments_fromstring(text)
    # 2. substract styles & statics
    styles = [root for root in roots if root.tag == "style"] + \
             [style.drop_tree() or style for root in roots for style in root.xpath(".//style")]
    for style in styles: 
        if style.get("type") is "text/scss": style.text = sass.compile(string=style.text)
    poststatics = [root for root in roots if root.tag == "static" and "post" in root.attrib] + \
                  [static.drop_tree() or static for root in roots for static in root.xpath(".//static") if "post" in static.attrib]
    prestatics = [root for root in roots if root.tag == "static" and "pre" in root.attrib] + \
                 [static.drop_tree() or static for root in roots for static in root.xpath(".//static") if "pre" in static.attrib]
    roots = list(filter(lambda x: x.tag not in ("style", "static"), roots))
    if path not in statics: statics[path] = (styles, poststatics, prestatics)
    # 3. replace imports
    for imp in (imp for root in roots for imp in root.xpath("//import")):
        ipath = os.path.join(os.path.dirname(path), imp.get("path"))
        importing_roots = compile(ipath, variables=imp.attrib, innerhtmls=imp, isroot=False, statics=statics)
        if len(importing_roots) == 1:
            importing_roots[0].attrib.update(imp.attrib)
        if imp in roots:
            imp_index = roots.index(imp)
            roots = list(filter(lambda x: x!=imp, roots))
            for i, root in enumerate(importing_roots):
                roots.insert(imp_index + i, root)
        else:
            imp_parent = imp.getparent()
            imp_index = imp_parent.index(imp)
            imp.drop_tree()
            for i, root in enumerate(importing_roots):
                imp_parent.insert(imp_index + i, root)
    # 4. replace innerhtmls
    innerhtml_map = {innerhtml.get("id", i):innerhtml for i, innerhtml in enumerate(innerhtmls)}
    target_innerhtmls = [innerhtml for root in roots for innerhtml in root.xpath(".//innerhtml")]
    for i, target_innerhtml in enumerate(target_innerhtmls):
        id_ = target_innerhtml.get("id", i)
        if id_ in innerhtml_map: 
            innerhtml_map[id_].attrib.update(target_innerhtml.attrib)
            target_innerhtml.getparent().replace(target_innerhtml, innerhtml_map[id_])
        else: target_innerhtml.drop_tree()
    # 5. if this is a root: put statics and return string
    if isroot:
        head = roots[0].xpath("//head")[0]
        body = roots[0].xpath("//body")[0]
        etree.SubElement(head, "style").text = "".join((sass.compile(string=dom2innerstr(style)) if style.get("type", "text/css") == "text/scss" else dom2innerstr(style)) \
            for i in statics for style in statics[i][0])
        for i in statics:
            for poststatic in statics[i][1]: body.append(poststatic)
            for prestatic in statics[i][2]: head.append(prestatic)
        return "".join(dom2str(root) for root in roots)
    else: return roots

if __name__ == "__main__":
    from optparse import OptionParser
    parser = OptionParser(usage="usage: %prog [options] filename", 
                          version="%prog {}".format(VERSION))
    parser.add_option("-c", "--src", dest="source",
                      help="source html path", metavar="SRC")
    parser.add_option("-o", "--out",
                      action="store_false", dest="out", default="a.html",
                      help="destination of output", metavar="OUT")
    parser.add_option("-C", "--srcdir", dest="sourcedir",
                      help="source dir path(it filters html files automatically)", default="src", metavar="SRCDIR")
    parser.add_option("-O", "--outdir", dest="outdir", default="build",
                      help="out dir path", metavar="OUTDIR")
    (option, tags) = parser.parse_args()
    if tags:
        print(compile(tags[0]))
    else:
        if option.source:
            with open(option.out, "w") as f:
                f.write(compile(tags[0]))
        elif option.sourcedir:
            compilables = [os.path.join(d, f) for (d, _, fs) in os.walk(option.sourcedir) for f in fs if f.endswith(".html")]
            if not os.path.exists(option.outdir):
                os.makedirs(option.outdir)
            for source in compilables:
                with open(os.path.join(option.outdir, os.path.basename(source)), "w") as f:
                    f.write(compile(source))
