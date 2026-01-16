package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strconv"
)

func main() {
	constType := flag.String("constant-type", "", "name of the constant type to filter, e.g, ErrorKind")

	flag.Usage = func() {
		fmt.Fprintf(flag.CommandLine.Output(),
			"Usage: %s [options] <file.go>\n",
			flag.CommandLine.Name())
		flag.PrintDefaults()
	}

	flag.Parse()

	if flag.NArg() != 1 {
		flag.Usage()
		os.Exit(1)
	}

	file := flag.Arg(0)

	fset := token.NewFileSet()
	node, err := parser.ParseFile(fset, file, nil, 0)
	if err != nil {
		panic(err)
	}

	constants := make(map[string]interface{})

	for _, decl := range node.Decls {
		gen, ok := decl.(*ast.GenDecl)
		if !ok || gen.Tok != token.CONST {
			continue
		}

		for _, spec := range gen.Specs {
			valSpec := spec.(*ast.ValueSpec)

			if *constType != "" {
				// Checking if a --constant-type argument is specified would be
				// better but that's a good start.
				if valSpec.Type == nil {
					continue
				}
				ident, ok := valSpec.Type.(*ast.Ident)
				if !ok || ident.Name != *constType {
					continue
				}
			}

			// Extract literal values
			for i, name := range valSpec.Names {
				if i >= len(valSpec.Values) {
					continue
				}

				value := literalValue(valSpec.Values[i])
				if value != nil {
					constants[name.Name] = value
				}
			}
		}
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	_ = enc.Encode(constants)
}

func literalValue(expr ast.Expr) interface{} {
	switch v := expr.(type) {

	case *ast.BasicLit:
		switch v.Kind {
		case token.STRING:
			s, err := strconv.Unquote(v.Value)
			if err == nil {
				return s
			}
		}
	}

	return nil
}
