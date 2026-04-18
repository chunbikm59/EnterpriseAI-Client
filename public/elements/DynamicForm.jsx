// ── ReviewPanel ─────────────────────────────────────────────────────────────
function ReviewPanel({ questions, answers, otherTexts, onGoToTab, onSubmit, onCancel }) {
  function renderAnswer(q) {
    const ans = answers[q.id];
    if (!ans) return React.createElement('span', { className: "text-muted-foreground text-xs" }, "（未回答）");

    if (q.type === "date") {
      return React.createElement('span', { className: "text-sm" }, ans.value || "（未選擇）");
    }

    if (q.type === "single_choice") {
      const display = ans.value === "__other__"
        ? ("其他：" + (otherTexts[q.id] || ""))
        : ans.value;
      return React.createElement('span', { className: "text-sm" }, display || "（未選擇）");
    }

    if (q.type === "multi_choice" || q.type === "multi_select_dropdown") {
      const items = [...(ans.value || [])];
      if (otherTexts[q.id]) items.push("其他：" + otherTexts[q.id]);
      if (items.length === 0) return React.createElement('span', { className: "text-muted-foreground text-xs" }, "（未選擇）");
      return React.createElement(
        'div', { className: "flex flex-wrap gap-1 mt-1" },
        ...items.map(v =>
          React.createElement('span', {
            key: v,
            className: "text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20"
          }, v)
        )
      );
    }
    return null;
  }

  const allRequiredAnswered = questions
    .filter(q => q.required)
    .every(q => {
      const ans = answers[q.id];
      if (!ans) return false;
      if (q.type === "single_choice") {
        return !!(ans.value && (ans.value !== "__other__" || otherTexts[q.id]));
      }
      if (q.type === "multi_choice" || q.type === "multi_select_dropdown") {
        return (ans.value && ans.value.length > 0) || !!otherTexts[q.id];
      }
      if (q.type === "date") return !!ans.value;
      return false;
    });

  return React.createElement(
    'div', { className: "space-y-3" },

    React.createElement('h3', { className: "text-sm font-semibold text-foreground mb-3" }, "回顧您的答案"),

    ...questions.map((q, idx) =>
      React.createElement(
        'div', {
          key: q.id,
          className: "flex items-start justify-between gap-2 rounded-lg border border-border p-3"
        },
        React.createElement(
          'div', { className: "flex-1 min-w-0" },
          React.createElement('p', { className: "text-xs text-muted-foreground mb-1 truncate" },
            (q.header || ("Q" + (idx + 1))) + "：" + q.question
          ),
          renderAnswer(q)
        ),
        React.createElement(
          'button', {
            onClick: () => onGoToTab(idx),
            className: "text-xs text-primary hover:underline shrink-0 ml-2"
          },
          "修改"
        )
      )
    ),

    !allRequiredAnswered && React.createElement(
      'p', { className: "text-xs text-red-500 mt-1" },
      "有必填題目（*）尚未完成，請返回補填。"
    ),

    React.createElement(
      'div', { className: "flex gap-2 pt-2 border-t border-border mt-3" },
      React.createElement(
        'button', {
          onClick: onSubmit,
          disabled: !allRequiredAnswered,
          className: "flex-1 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-opacity hover:opacity-90"
        },
        "提交"
      ),
      React.createElement(
        'button', {
          onClick: onCancel,
          className: "px-5 py-2 text-sm rounded-lg border border-border hover:bg-accent transition-colors"
        },
        "取消"
      )
    )
  );
}


// ── QuestionPanel ────────────────────────────────────────────────────────────
function QuestionPanel({ q, answers, otherTexts, setOtherTexts, onSingleChoice, onSingleChoiceOther, onMultiChoice, onDate, onConfirm }) {
  const ans = answers[q.id];

  // single_choice
  if (q.type === "single_choice") {
    const optionButtons = (q.options || []).map(opt => {
      const selected = ans && ans.value === opt.label;
      return React.createElement(
        'button', {
          key: opt.label,
          onClick: () => onSingleChoice(q, opt.label),
          className: "w-full text-left px-4 py-3 rounded-lg border text-sm transition-all " +
            (selected
              ? "border-primary bg-primary/10 text-foreground font-medium ring-1 ring-primary"
              : "border-border hover:border-primary/50 hover:bg-accent")
        },
        React.createElement('span', { className: "font-medium" }, opt.label),
        opt.description && React.createElement(
          'span', { className: "text-muted-foreground ml-2 text-xs" },
          "— " + opt.description
        )
      );
    });

    // 其他選項
    const otherSelected = ans && ans.value === "__other__";
    const otherBlock = q.other_option && React.createElement(
      'div', {
        className: "rounded-lg border p-3 transition-colors " +
          (otherSelected ? "border-primary bg-primary/10" : "border-border hover:border-primary/50")
      },
      React.createElement(
        'button', {
          onClick: () => onSingleChoiceOther(q),
          className: "text-sm w-full text-left " + (otherSelected ? "text-foreground font-medium" : "text-muted-foreground")
        },
        "其他"
      ),
      otherSelected && React.createElement(
        'div', { className: "mt-2" },
        React.createElement('input', {
          type: "text",
          className: "w-full text-sm bg-transparent border-b border-border outline-none focus:border-primary px-1 py-0.5 transition-colors",
          placeholder: "請輸入...",
          value: otherTexts[q.id] || "",
          onChange: e => setOtherTexts(prev => ({ ...prev, [q.id]: e.target.value })),
          autoFocus: true,
        }),
        React.createElement(
          'button', {
            onClick: onConfirm,
            disabled: !otherTexts[q.id],
            className: "mt-2 px-3 py-1 text-xs rounded bg-primary text-primary-foreground disabled:opacity-40 disabled:cursor-not-allowed"
          },
          "確認"
        )
      )
    );

    return React.createElement(
      'div', { className: "space-y-2" },
      ...optionButtons,
      otherBlock
    );
  }

  // multi_choice
  if (q.type === "multi_choice") {
    const selectedValues = (ans && ans.value) || [];
    const checkboxItems = (q.options || []).map(opt => {
      const checked = selectedValues.includes(opt.label);
      return React.createElement(
        'label', {
          key: opt.label,
          className: "flex items-start gap-3 px-4 py-3 rounded-lg border cursor-pointer transition-all " +
            (checked ? "border-primary bg-primary/10" : "border-border hover:border-primary/50 hover:bg-accent")
        },
        React.createElement('input', {
          type: "checkbox",
          checked: checked,
          onChange: e => onMultiChoice(q, opt.label, e.target.checked),
          className: "mt-0.5 accent-primary shrink-0",
        }),
        React.createElement(
          'div', null,
          React.createElement('span', { className: "text-sm font-medium" }, opt.label),
          opt.description && React.createElement(
            'p', { className: "text-xs text-muted-foreground mt-0.5" }, opt.description
          )
        )
      );
    });

    const otherChecked = !!otherTexts[q.id];
    const otherBlock = q.other_option && React.createElement(
      'div', {
        className: "px-4 py-3 rounded-lg border transition-colors " +
          (otherChecked ? "border-primary bg-primary/10" : "border-border hover:border-primary/50")
      },
      React.createElement(
        'label', { className: "flex items-center gap-2 cursor-pointer" },
        React.createElement('input', {
          type: "checkbox",
          checked: otherChecked,
          onChange: e => {
            if (!e.target.checked) setOtherTexts(prev => ({ ...prev, [q.id]: "" }));
          },
          className: "accent-primary",
        }),
        React.createElement('span', { className: "text-sm " + (otherChecked ? "font-medium" : "text-muted-foreground") }, "其他")
      ),
      React.createElement('input', {
        type: "text",
        className: "mt-2 w-full text-sm bg-transparent border-b border-border outline-none focus:border-primary px-1 py-0.5 transition-colors",
        placeholder: "請輸入...",
        value: otherTexts[q.id] || "",
        onChange: e => setOtherTexts(prev => ({ ...prev, [q.id]: e.target.value })),
      })
    );

    const hasAnswer = selectedValues.length > 0 || !!otherTexts[q.id];

    return React.createElement(
      'div', { className: "space-y-2" },
      ...checkboxItems,
      otherBlock,
      React.createElement(
        'button', {
          onClick: onConfirm,
          disabled: !hasAnswer && q.required,
          className: "mt-2 w-full py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-opacity hover:opacity-90"
        },
        "確認並繼續 →"
      )
    );
  }

  // multi_select_dropdown
  if (q.type === "multi_select_dropdown") {
    const selectedValues = (ans && ans.value) || [];
    const [dropdownOpen, setDropdownOpen] = React.useState(false);
    const options = q.options || [];

    const toggleOption = (label) => {
      onMultiChoice(q, label, !selectedValues.includes(label));
    };

    const displayText = selectedValues.length === 0
      ? "請選擇（可複選）"
      : selectedValues.join("、");

    const hasAnswer = selectedValues.length > 0 || !!otherTexts[q.id];

    return React.createElement(
      'div', { className: "space-y-2" },

      // 下拉觸發按鈕
      React.createElement(
        'div', { className: "relative" },

        React.createElement(
          'button', {
            onClick: () => setDropdownOpen(prev => !prev),
            className: "w-full flex items-center justify-between px-4 py-2.5 rounded-lg border text-sm transition-all " +
              (dropdownOpen ? "border-primary ring-1 ring-primary" : "border-border hover:border-primary/50"),
          },
          React.createElement(
            'span', {
              className: selectedValues.length === 0 ? "text-muted-foreground" : "text-foreground"
            },
            displayText
          ),
          React.createElement(
            'span', { className: "text-muted-foreground ml-2 transition-transform " + (dropdownOpen ? "rotate-180" : "") },
            "▾"
          )
        ),

        // 下拉選單
        dropdownOpen && React.createElement(
          'div', {
            className: "absolute z-10 mt-1 w-full rounded-lg border border-border bg-card shadow-lg overflow-hidden"
          },
          ...options.map(opt => {
            const checked = selectedValues.includes(opt.label);
            return React.createElement(
              'label', {
                key: opt.label,
                className: "flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors hover:bg-accent " +
                  (checked ? "bg-primary/5" : "")
              },
              React.createElement('input', {
                type: "checkbox",
                checked: checked,
                onChange: () => toggleOption(opt.label),
                className: "accent-primary shrink-0",
              }),
              React.createElement(
                'div', null,
                React.createElement('span', { className: "text-sm " + (checked ? "font-medium" : "") }, opt.label),
                opt.description && React.createElement(
                  'p', { className: "text-xs text-muted-foreground" }, opt.description
                )
              )
            );
          }),
          // 其他選項
          q.other_option && React.createElement(
            'div', {
              className: "px-4 py-2.5 border-t border-border"
            },
            React.createElement(
              'label', { className: "flex items-center gap-3 cursor-pointer" },
              React.createElement('input', {
                type: "checkbox",
                checked: !!otherTexts[q.id],
                onChange: e => {
                  if (!e.target.checked) setOtherTexts(prev => ({ ...prev, [q.id]: "" }));
                },
                className: "accent-primary shrink-0",
              }),
              React.createElement('span', { className: "text-sm text-muted-foreground" }, "其他")
            ),
            React.createElement('input', {
              type: "text",
              className: "mt-1.5 w-full text-sm bg-transparent border-b border-border outline-none focus:border-primary px-1 py-0.5 transition-colors",
              placeholder: "請輸入...",
              value: otherTexts[q.id] || "",
              onChange: e => setOtherTexts(prev => ({ ...prev, [q.id]: e.target.value })),
            })
          )
        )
      ),

      // 已選標籤列
      selectedValues.length > 0 && React.createElement(
        'div', { className: "flex flex-wrap gap-1.5" },
        ...selectedValues.map(v =>
          React.createElement(
            'span', {
              key: v,
              className: "inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20"
            },
            v,
            React.createElement(
              'button', {
                onClick: () => onMultiChoice(q, v, false),
                className: "ml-0.5 hover:text-red-500 transition-colors leading-none"
              },
              "×"
            )
          )
        )
      ),

      // 確認按鈕
      React.createElement(
        'button', {
          onClick: onConfirm,
          disabled: !hasAnswer && q.required,
          className: "mt-1 w-full py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-opacity hover:opacity-90"
        },
        "確認並繼續 →"
      )
    );
  }

  // date
  if (q.type === "date") {
    const dateValue = (ans && ans.value) || "";
    return React.createElement(
      'div', { className: "space-y-3" },
      React.createElement('input', {
        type: "date",
        value: dateValue,
        onChange: e => onDate(q, e.target.value),
        className: "text-sm border border-border rounded-lg px-3 py-2 bg-background text-foreground focus:outline-none focus:border-primary transition-colors",
      }),
      dateValue && React.createElement(
        'button', {
          onClick: onConfirm,
          className: "px-5 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-90"
        },
        "確認並繼續 →"
      )
    );
  }

  return React.createElement('p', { className: "text-sm text-muted-foreground" }, "不支援的題型：" + q.type);
}


// ── DynamicForm（主元件） ─────────────────────────────────────────────────────
export default function DynamicForm() {
  const title = props.title || "問卷";
  const description = props.description || "";
  const questions = props.questions || [];
  const formId = props.form_id || "";
  const submittedFromProps = props.submitted || false;

  const [activeTab, setActiveTab] = React.useState(0);
  const [answers, setAnswers] = React.useState({});
  const [otherTexts, setOtherTexts] = React.useState({});
  const [finalSubmitted, setFinalSubmitted] = React.useState(false);
  const [cancelled, setCancelled] = React.useState(false);

  const totalTabs = questions.length + 1; // 問題 tabs + 確認 tab

  function isAnswered(q) {
    const ans = answers[q.id];
    if (!ans) {
      // date / single_choice: 若有 otherText 也算
      if (q.type === "single_choice") return !!otherTexts[q.id];
      return false;
    }
    if (q.type === "single_choice") {
      return !!(ans.value && (ans.value !== "__other__" || otherTexts[q.id]));
    }
    if (q.type === "multi_choice" || q.type === "multi_select_dropdown") {
      return (ans.value && ans.value.length > 0) || !!otherTexts[q.id];
    }
    if (q.type === "date") return !!ans.value;
    return false;
  }

  function goNext() {
    if (activeTab < totalTabs - 1) {
      setActiveTab(prev => prev + 1);
    }
  }

  function handleSingleChoice(q, label) {
    setAnswers(prev => ({ ...prev, [q.id]: { type: "single_choice", value: label } }));
    setTimeout(() => setActiveTab(prev => Math.min(prev + 1, totalTabs - 1)), 280);
  }

  function handleSingleChoiceOther(q) {
    setAnswers(prev => ({ ...prev, [q.id]: { type: "single_choice", value: "__other__" } }));
  }

  function handleMultiChoice(q, label, checked) {
    setAnswers(prev => {
      const current = (prev[q.id] && prev[q.id].value) || [];
      const newVal = checked ? [...current, label] : current.filter(v => v !== label);
      return { ...prev, [q.id]: { type: "multi_choice", value: newVal } };
    });
  }

  function handleDate(q, value) {
    setAnswers(prev => ({ ...prev, [q.id]: { type: "date", value } }));
  }

  function buildFinalAnswers() {
    const result = {};
    questions.forEach(q => {
      const ans = answers[q.id];
      if (q.type === "single_choice") {
        result[q.id] = ans && ans.value === "__other__"
          ? { value: "__other__", other_text: otherTexts[q.id] || "" }
          : { value: (ans && ans.value) || null };
      } else if (q.type === "multi_choice" || q.type === "multi_select_dropdown") {
        result[q.id] = {
          value: (ans && ans.value) || [],
          other_text: otherTexts[q.id] || ""
        };
      } else if (q.type === "date") {
        result[q.id] = { value: (ans && ans.value) || null };
      }
    });
    return result;
  }

  function handleSubmit() {
    setFinalSubmitted(true);
    callAction({
      name: "submit_dynamic_form",
      payload: {
        form_id: formId,
        answers: buildFinalAnswers(),
        cancelled: false,
      }
    });
  }

  function handleCancel() {
    setCancelled(true);
    callAction({
      name: "submit_dynamic_form",
      payload: {
        form_id: formId,
        answers: {},
        cancelled: true,
      }
    });
  }

  // 已提交（本地或由 props 通知）
  if (finalSubmitted || submittedFromProps) {
    return React.createElement(
      'div', { className: "rounded-xl border border-border bg-card p-6 max-w-2xl text-center" },
      React.createElement('div', { className: "text-green-600 dark:text-green-400 font-semibold text-base mb-1" }, "✓ 已提交"),
      React.createElement('p', { className: "text-sm text-muted-foreground" }, "表單已成功提交，請等待 AI 回應。")
    );
  }

  if (cancelled) {
    return React.createElement(
      'div', { className: "rounded-xl border border-border bg-card p-4 max-w-2xl text-center" },
      React.createElement('div', { className: "text-muted-foreground text-sm" }, "已取消")
    );
  }

  const isLastTab = activeTab === totalTabs - 1;
  const currentQ = !isLastTab ? questions[activeTab] : null;

  return React.createElement(
    'div', { className: "rounded-xl border border-border bg-card p-4 max-w-2xl w-full" },

    // 標題
    React.createElement(
      'div', { className: "mb-4" },
      React.createElement('h2', { className: "text-base font-semibold text-foreground" }, title),
      description && React.createElement('p', { className: "text-sm text-muted-foreground mt-0.5" }, description)
    ),

    // Tab 導航列
    React.createElement(
      'div', { className: "flex items-center gap-1.5 mb-4 flex-wrap border-b border-border pb-3" },
      ...questions.map((q, idx) => {
        const answered = isAnswered(q);
        const active = activeTab === idx;
        return React.createElement(
          'button', {
            key: q.id,
            onClick: () => setActiveTab(idx),
            className: "px-3 py-1 rounded-full text-xs font-medium transition-all " + (
              active
                ? "bg-primary text-primary-foreground shadow-sm"
                : answered
                  ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300 border border-green-200 dark:border-green-700"
                  : "bg-muted text-muted-foreground hover:bg-accent border border-transparent"
            )
          },
          (answered && !active ? "✓ " : "") + (q.header || ("Q" + (idx + 1)))
        );
      }),
      // 確認提交 tab
      React.createElement(
        'button', {
          onClick: () => setActiveTab(totalTabs - 1),
          className: "px-3 py-1 rounded-full text-xs font-medium transition-all " + (
            isLastTab
              ? "bg-primary text-primary-foreground shadow-sm"
              : "bg-muted text-muted-foreground hover:bg-accent border border-transparent"
          )
        },
        "確認提交"
      )
    ),

    // 問題標題
    !isLastTab && currentQ && React.createElement(
      'div', { className: "mb-3" },
      React.createElement(
        'p', { className: "text-sm font-medium text-foreground leading-relaxed" },
        currentQ.question,
        currentQ.required && React.createElement('span', { className: "text-red-500 ml-1" }, "*")
      )
    ),

    // 題目內容 or 確認頁
    !isLastTab && currentQ
      ? React.createElement(QuestionPanel, {
          q: currentQ,
          answers,
          otherTexts,
          setOtherTexts,
          onSingleChoice: handleSingleChoice,
          onSingleChoiceOther: handleSingleChoiceOther,
          onMultiChoice: handleMultiChoice,
          onDate: handleDate,
          onConfirm: goNext,
        })
      : React.createElement(ReviewPanel, {
          questions,
          answers,
          otherTexts,
          onGoToTab: setActiveTab,
          onSubmit: handleSubmit,
          onCancel: handleCancel,
        }),

    // 底部導航（非最後一頁才顯示）
    !isLastTab && React.createElement(
      'div', { className: "flex justify-between mt-4 pt-3 border-t border-border" },
      React.createElement(
        'button', {
          onClick: () => setActiveTab(prev => Math.max(prev - 1, 0)),
          disabled: activeTab === 0,
          className: "text-xs text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        },
        "← 上一題"
      ),
      React.createElement(
        'span', { className: "text-xs text-muted-foreground" },
        (activeTab + 1) + " / " + questions.length
      ),
      React.createElement(
        'button', {
          onClick: goNext,
          className: "text-xs text-muted-foreground hover:text-foreground transition-colors"
        },
        "下一題 →"
      )
    )
  );
}
