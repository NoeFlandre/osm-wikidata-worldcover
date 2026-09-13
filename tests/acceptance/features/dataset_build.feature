Feature: Building a supervised text to land-cover dataset
  As a benchmark author
  I want OSM polygons labelled by the land cover that dominates them
  So that linked articles can be used to train and evaluate text classifiers

  Background:
    Given a land cover map whose western half is tree cover and eastern half is built-up

  Scenario: A polygon dominated by one class becomes an example
    Given a polygon lying wholly in the tree cover half
    And the polygon is linked to an article of 40 words
    When I build the dataset
    Then the dataset contains 1 example
    And the example is labelled "Tree cover"
    And the example's dominant fraction is at least 0.8

  Scenario: A polygon split evenly between two classes is refused
    Given a polygon spanning both halves equally
    And the polygon is linked to an article of 40 words
    When I build the dataset
    Then the dataset is empty
    And the polygon was rejected because "below_threshold"

  Scenario: A polygon that was mostly not observed is refused
    Given a land cover map whose southern half is unobserved
    And a polygon covering the whole map
    And the polygon is linked to an article of 40 words
    When I build the dataset
    Then the dataset is empty
    And the polygon was rejected because "below_threshold"

  Scenario: An article too short to carry signal is dropped
    Given a polygon lying wholly in the tree cover half
    And the polygon is linked to an article of 3 words
    When I build the dataset
    Then the dataset is empty

  Scenario: One example is produced per polygon-document pair
    Given a polygon lying wholly in the tree cover half
    And the polygon is linked to 3 distinct articles of 40 words
    When I build the dataset
    Then the dataset contains 3 examples
    And every example names the same polygon

  Scenario: The same place appearing in two regional extracts is kept once
    Given a polygon lying wholly in the tree cover half
    And the polygon is linked to an article of 40 words
    And the identical OSM object also appears in a neighbouring region
    When I build the dataset
    Then the dataset contains 1 example

  Scenario: Nearby places never straddle a split
    Given 40 polygons scattered within one kilometre, each with its own article
    When I build the dataset
    Then every example shares a single split
    And no polygon appears in more than one split
    And no document appears in more than one split

  Scenario: A finished build satisfies every published guarantee
    Given 40 polygons scattered within one kilometre, each with its own article
    When I build the dataset
    Then the build reports no violations
    And every label is a real WorldCover class

  Scenario: Rebuilding the same inputs produces the same bytes
    Given 40 polygons scattered within one kilometre, each with its own article
    When I build the dataset twice
    Then both builds produce byte-identical files
