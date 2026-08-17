## Ticket 017 - Parsing 
## Location

Main implementation:

    app/ingestion/parsing.py

Local test:

    tests/test_parsing_local.py

Test documents:

    tests/test_documents/

## Parsed Document Structure

The parser returns:

    ParsedDocument

which contains:

    sections: list[DocumentSection]


Each section contains:

    type
    content
    metadata


### Section Types

The current section types are:

    heading
    paragraph
    table