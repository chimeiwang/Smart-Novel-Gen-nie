package cn.inkforge.core.workflows.domain;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 全部 patch 都在同一原候选定位；任何不确定性都不产生部分结果。 */
public final class ChapterDraftPatches {
    private ChapterDraftPatches() {}
    public record Proposal(String find, String replace, Integer startCodePoint, Integer endCodePoint) {}
    private record Located(int start, int end, Proposal proposal) {}
    public static final class Rejected extends IllegalArgumentException {
        public Rejected(String code) { super(code); }
    }

    public static String apply(String content, List<Proposal> proposals) {
        if (proposals.isEmpty()) throw new Rejected("PATCH_ARTIFACT_UNSUPPORTED");
        Map<String, Located> unique = new LinkedHashMap<>();
        for (Proposal proposal : proposals) {
            if (proposal.find() == null || proposal.find().isEmpty() || proposal.replace() == null
                    || (proposal.startCodePoint() == null) != (proposal.endCodePoint() == null)) throw new Rejected("PATCH_ARTIFACT_UNSUPPORTED");
            int start = content.indexOf(proposal.find());
            if (start < 0) throw new Rejected("PATCH_TARGET_NOT_FOUND");
            if (content.indexOf(proposal.find(), start + 1) >= 0) throw new Rejected("PATCH_TARGET_AMBIGUOUS");
            int end = start + proposal.find().length();
            if (proposal.startCodePoint() != null && (content.codePointCount(0, start) != proposal.startCodePoint()
                    || content.codePointCount(0, end) != proposal.endCodePoint())) throw new Rejected("PATCH_RANGE_MISMATCH");
            Located previous = unique.putIfAbsent(proposal.find(), new Located(start, end, proposal));
            if (previous != null && !previous.proposal().replace().equals(proposal.replace())) throw new Rejected("PATCH_CONFLICT");
        }
        if (unique.size() > 20) throw new Rejected("PATCH_COUNT_EXCEEDED");
        List<Located> ordered = new ArrayList<>(unique.values());
        ordered.sort(Comparator.comparingInt(Located::start));
        for (int index = 1; index < ordered.size(); index++) {
            if (ordered.get(index).start() < ordered.get(index - 1).end()) throw new Rejected("PATCH_OVERLAP");
        }
        StringBuilder result = new StringBuilder(content);
        for (Located located : ordered.reversed()) result.replace(located.start(), located.end(), located.proposal().replace());
        try {
            return DurableChapterDraftArtifact.nonBlank(result.toString());
        } catch (IllegalArgumentException exception) {
            throw new Rejected("PATCH_EMPTY_CONTENT");
        }
    }
}
