import main


def test_split_text_search_terms_treats_common_separators_as_delimiters():
    assert main._split_text_search_terms(" IT_YEDEK ") == ["IT", "YEDEK"]
    assert main._split_text_search_terms("TRIST-MC/PC.01") == ["TRIST", "MC", "PC", "01"]


def test_searchable_column_lookup_accepts_collapsed_aliases():
    assert main.SEARCHABLE_COLUMN_LOOKUP["namesurname"] == ("[Name_Surname]", "word_prefix_like")
    assert main.SEARCHABLE_COLUMN_LOOKUP["windowscomputername"] == ("[Windows_Computer_Name]", "like")


def test_append_filter_uses_word_prefix_matching_for_name_surname():
    clauses = []
    params = []

    main._append_filter(clauses, params, "[Name_Surname]", "word_prefix_like", "IT_YEDEK")

    assert len(clauses) == 1
    assert clauses[0].count("LIKE ?") == 4
    assert " AND " in clauses[0]
    assert params == ["IT%", "% IT%", "YEDEK%", "% YEDEK%"]
