// Extract the actual Chordino dictionary without audio or model inference.
// Link against the pinned upstream chromamethods.cpp; do not reconstruct profiles.
#include "chromamethods.h"
#include <iomanip>
#include <iostream>
#include <limits>

int main() {
    std::vector<float> profiles;
    std::vector<std::vector<int>> notes;
    const auto labels = chordDictionary(&profiles, &notes, 0.1f, 0.0f);
    if (profiles.size() != labels.size() * 24 || notes.size() != labels.size()) return 1;
    std::cout << std::setprecision(std::numeric_limits<float>::max_digits10);
    std::cout << "[\n";
    for (size_t i = 0; i < labels.size(); ++i) {
        if (i) std::cout << ",\n";
        std::cout << "{\"index\":" << i << ",\"label\":" << std::quoted(labels[i]) << ",\"weights\":[";
        for (size_t j = 0; j < 24; ++j) {
            if (j) std::cout << ",";
            std::cout << profiles[i * 24 + j];
        }
        std::cout << "]}";
    }
    std::cout << "\n]\n";
}
