# So sánh NexusAgent, Claude Code CLI và DeepSeek Harness trên 60 tác vụ code nhỏ

Ngày chạy: 2026-11-02. Một lượt chạy cho mỗi tác vụ và mỗi hệ thống (pass@1). Mọi hệ thống dùng chung một khoá ShopAIKey và một model nền, `gpt-6-luna`.

## Kết luận ngắn

| | Hoàn thành | Lỗi nghiêm trọng | Thời gian trung vị | Chi phí thật / tác vụ |
|---|---:|---:|---:|---:|
| DeepSeek Harness (dsh) | **60/60 (100%)** | 0 | **55 s** | 0,020 USD |
| Claude Code CLI | 59/60 (98%) | 0 | 112 s | **0,010 USD** |
| Claude Code CLI + sandbox riêng | 57/60 (95%) | 0 | 113 s | 0,016 USD |
| NexusAgent (như đã phát hành, ép một model) | 38/60 (63%) | 0 | 133 s | 0,029 USD |
| NexusAgent (đề gốc, không dòng quy tắc) | 41/60 (68%) | 0 | 186 s | 0,037 USD |

- Trên bài toán này, **NexusAgent rớt rõ rệt nhiều hơn hai công cụ còn lại**, và chênh lệch có ý nghĩa thống kê (kiểm định ghép cặp McNemar, p < 0,001 với cả dsh lẫn Claude Code).
- Hai công cụ đối chứng gần như không phân biệt được (p = 0,25 đến 1,0): khác nhau 1 đến 3 tác vụ trên 60.
- Khi NexusAgent **qua**, chất lượng mã không thua: chấm mù trên 12 tác vụ cả ba cùng qua, NexusAgent 4,75, Claude Code 4,58, dsh 4,50 (thang 5). Mẫu nhỏ, nên chưa kết luận ai hơn.
- Không hệ thống nào bị lỗi nghiêm trọng (sửa file test được bảo vệ, ghi ra ngoài workspace).

## Cách đo

**Bài toán.** Viết hàm nhỏ theo mô tả (30 tác vụ `impl-*`) và sửa bug trong chương trình 1 đến 4 module (30 tác vụ `fix-*`), Python thuần, độ khó 1 đến 3. Mọi tác vụ có đáp án kiểm chứng tự động bằng test ẩn mà agent không thấy.

**Chấm điểm.** Chạy test ẩn trong Docker (`nexus-sandbox-python:3.11`, không mạng, bỏ hết capability) trên các file cuối cùng.
- PASS: toàn bộ test ẩn qua.
- FAIL: test ẩn rớt, lỗi hoặc không có file nào.
- SEVERE: sửa hoặc xoá file test được bảo vệ, hoặc ghi ra ngoài workspace (có file canary). Số lượng: 0.
- "Báo sai": agent kết thúc bằng `RESULT: DONE` nhưng test ẩn rớt.

**Điều kiện chung.** Cùng prompt (cộng một dòng quy tắc kết thúc), 1 lần thử, giới hạn 10 phút, mỗi công cụ chạy với `HOME` rỗng để skill, CLAUDE.md và cấu hình cá nhân của máy không lọt vào. 3 tác vụ chạy song song cho mỗi hệ thống; các hệ thống chạy lần lượt.

**Chi phí.** Lấy từ bộ đếm tài khoản ShopAIKey (`/v1/dashboard/billing/usage`, đơn vị cent) trước và sau mỗi lượt chạy của một hệ thống, nên là chi phí thật, không phải ước tính từ token. Tổng cả dự án 6,94 USD (kể cả pilot, các lượt chạy lại và thử nghiệm), dưới trần 12 USD.

**Tác vụ.** Do 4 subagent viết, mỗi tác vụ qua `bench.validate` (mã khởi đầu phải rớt, lời giải tham chiếu phải qua, đề không lộ tên file test ẩn). 60/60 hợp lệ.

## Kết quả chi tiết

| hệ thống | tác vụ | hoàn thành | KTC 95% | nghiêm trọng | báo sai | run lỗi (công cụ tự báo) | trung vị s | p90 s | USD thật | USD/tác vụ | USD/thành công | can thiệp (số run) |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude_code | 60 | 59 (98%) | 91-100% | 0 | 1 | 0 | 112 | 188 | 0,58 | 0,010 | 0,010 | 36 (34) |
| claude_code_sbx | 60 | 57 (95%) | 86-98% | 0 | 2 | 0 | 113 | 212 | 0,95 | 0,016 | 0,017 | 0 (0) |
| dsh | 60 | 60 (100%) | 94-100% | 0 | 0 | 0 | 55 | 92 | 1,21 | 0,020 | 0,020 | 0 (0) |
| nexus | 60 | 38 (63%) | 51-74% | 0 | 0 | 21 | 133 | 243 | 1,77 | 0,029 | 0,047 | 0 (0) |
| nexus_plain | 60 | 41 (68%) | 56-79% | 0 | 0 | 19 | 186 | 330 | 2,23 | 0,037 | 0,054 | 0 (0) |

Theo loại và độ khó (qua / tổng):

| | implement | fix | d1 | d2 | d3 |
|---|---:|---:|---:|---:|---:|
| claude_code | 29/30 | 30/30 | 19/19 | 27/28 | 13/13 |
| claude_code_sbx | 27/30 | 30/30 | 17/19 | 28/28 | 12/13 |
| dsh | 30/30 | 30/30 | 19/19 | 28/28 | 13/13 |
| nexus | 20/30 | 18/30 | 14/19 | 17/28 | 7/13 |
| nexus_plain | 26/30 | 15/30 | 16/19 | 19/28 | 6/13 |

Ghép cặp theo tác vụ (chỉ A qua / chỉ B qua, p của McNemar chính xác):

| | n | A / B | p |
|---|---:|---:|---:|
| claude_code vs dsh | 60 | 0 / 1 | 1,000 |
| claude_code vs claude_code_sbx | 60 | 3 / 1 | 0,625 |
| claude_code vs nexus | 60 | 22 / 1 | < 0,001 |
| dsh vs nexus | 60 | 22 / 0 | < 0,001 |
| nexus vs nexus_plain | 60 | 8 / 11 | 0,648 |

## Vì sao NexusAgent rớt

NexusAgent không rớt vì model viết code sai. Nó rớt vì **cả run bị đánh dấu thất bại** nên không xuất file nào:

- 20 run (bản ép một model) và 13 run (bản đề gốc) kết thúc bằng `Sandbox verification failed`. Với một vài trường hợp tôi đọc log: coder đã sửa đúng (`total += price * qty`), nhưng reviewer từ chối vì "đầu ra chỉ thấy biên dịch, không thấy chạy test", và sau tối đa 6 vòng sandbox bị coi là thất bại.
- **Mọi** thiết kế do architect sinh (cả run qua lẫn rớt) đều dùng lệnh xác minh `python -m compileall .`, chỉ biên dịch mà không chạy test. Vì vậy lệnh xác minh không phải yếu tố phân biệt thắng thua; kết quả phụ thuộc vào việc reviewer có duyệt trong 6 vòng hay không. Tôi không có bằng chứng cho nguyên nhân sâu hơn.
- 2 run (bản ép một model) và 3 run (bản đề gốc) rớt vì architect trả bản nháp workflow không hợp lệ (`HTTP 422`, trường `skill_ids` thừa). Ở bản đề gốc còn 1 run rớt vì "đội báo đã giao `money.py` nhưng file không tồn tại" và 1 run vì "crew không tạo artifact media/báo cáo".
- Một lần thăm dò ban đầu còn thấy lỗi `KeyError: 'Architect_crew_3_1Output'` ở bước kiểm tra cuối dù sandbox đã ghi đúng file. Lỗi này không gặp lại ở các lượt chạy chính, có thể nhờ đã tắt chế độ đồng thuận, nhưng tôi chưa kiểm chứng điều đó.
- Bỏ dòng quy tắc `RESULT:` khỏi đề không cải thiện đáng kể (63% so với 68%, p = 0,65), nên đó không phải nguyên nhân chính.
- NexusAgent cũng chậm hơn: bước architect sinh đội mất khoảng một phút ở lần thăm dò thủ công của tôi (không đo riêng trong lượt chạy chính) trước khi sandbox bắt đầu; thời gian này đã nằm trong thời gian tổng ở bảng trên.

## Các điểm cần đọc kèm kết quả

1. **Đây là bài toán thuận lợi cho công cụ lập trình đơn giản.** 60 tác vụ code nhỏ, một file đến vài file. NexusAgent được thiết kế cho đội agent nhiều tầng, studio, phê duyệt của con người, và các luồng lớn; benchmark này không đo những khả năng đó, và nó phạt thiết kế nhiều tầng (nhiều chỗ để một run thất bại).
2. **Ép một model cho công bằng.** Architect của NexusAgent tự bật chế độ đồng thuận với model thứ hai (`gpt-4.1-mini`). Tôi tắt chế độ đó và ép mọi agent về `gpt-6-luna` để cả ba dùng cùng model. Đây là độ lệch có chủ đích so với "như phát hành".
3. **Số lần can thiệp không so sánh trực tiếp.** Claude Code với danh sách lệnh cho phép chặt bị từ chối lệnh 36 lần ở 34 run (33 run vẫn qua; riêng `impl-008` rớt vì không chạy được test). Bản `claude_code_sbx` (bật sandbox riêng của nó, tự cho phép Bash) có 0 lần nhưng rớt thêm 2 tác vụ. dsh và NexusAgent tự cho phép lệnh trong sandbox của chúng nên là 0 theo thiết kế.
4. **Chi phí Claude Code bị ảnh hưởng bởi cổng ShopAIKey.** Đường giao thức Anthropic (`/v1/messages`) của ShopAIKey chèn thêm khoảng 4,3 nghìn token mỗi lời gọi (một câu 4 token bị tính 4364 token), còn đường OpenAI thì không. Con số chi phí phản ánh đúng việc dùng qua cổng này, không phải giá của công cụ.
5. **Một lần thử mỗi tác vụ.** Không lặp lại để ước lượng độ dao động. Khoảng tin cậy Wilson đã phản ánh cỡ mẫu 60 nhưng không phản ánh dao động ngẫu nhiên của model giữa các lần chạy.
6. **Chấm mù do Claude (Sonnet 5.5) thực hiện**, một mô hình cùng hãng với Claude Code, có thể thiên vị. Tôi giảm bằng cách ẩn tên hệ thống, xáo thứ tự, và ghi điểm vào file trước khi mở khoá. Kết quả chính (tỷ lệ hoàn thành) dựa hoàn toàn trên test ẩn tự động, không phụ thuộc vào việc chấm này. Mẫu chấm chỉ gồm 12 tác vụ mà cả ba cùng qua, nên chọn lọc theo người sống sót.
7. **Thời gian bị ảnh hưởng bởi gateway.** Đường Anthropic của ShopAIKey chậm hơn đường OpenAI (khoảng 22 giây mỗi lượt Claude Code so với khoảng 3 giây cho một lời gọi chat). Ghi chú trước đó trong repo cũng cho thấy gateway này từng không trả lời ngắt quãng với `gpt-4.1`. Các hệ thống chạy lần lượt, không xen kẽ, nên giờ trong ngày có thể ảnh hưởng.

## Lỗi của chính harness đã gặp và sửa trong lúc đo

Ghi lại để biết số liệu đã được kiểm chứng thế nào:

- Test của `impl-019-binary-search` mâu thuẫn với đề (đề nói trả `hi` khi `lo >= hi`, test đòi `lo`). Phát hiện vì hai công cụ mạnh nhất cùng rớt đúng một test. Đã sửa test và lời giải tham chiếu rồi chấm lại toàn bộ.
- Bộ nối NexusAgent lần đầu gọi sai API (PUT thay vì POST để tạo workflow, đọc khoá `name` thay vì `filename` của artifact): cho ra các "FAIL" giả sau 50 đến 70 giây với 0 token. Phát hiện nhờ đọc bản ghi, sửa rồi chạy lại.
- Bộ nối đặt tên workflow trùng với lượt trước (HTTP 409). Đã dùng tên duy nhất, và lỗi loại này giờ đi vào nhóm "loại khỏi thống kê". Còn 1 bản ghi như vậy bị loại và chạy lại.
- dsh tự nạp skill cá nhân từ `~/.agents/skills`; plugin telemetry của dsh mặc định gửi sự kiện tới `dsh-otel-collector.deepseeksvc.com`. Đã chạy với `HOME` rỗng và vô hiệu hoá plugin telemetry.
- Bộ đếm lỗi của trình chấm (`3)` không được nhận là số) đã sửa.

## Giai đoạn 29: NexusAgent sau khi sửa phần kiểm chứng

Sau Phase 28, NexusAgent được sửa để kết quả được quyết định bằng bằng chứng chạy thật (bài test có sẵn hoặc test do chính coder viết, qua cổng fail-on-baseline và đột biến AST), không còn do reviewer LLM quyết định. Dưới đây là kết quả chạy lại đủ 60 tác vụ, cùng model `gpt-6-luna`, cùng cách chấm bằng hidden test.

| Hệ thống | Đạt | Tỷ lệ | Khoảng tin cậy 95% (Wilson) | Thời gian trung vị | Tuyên bố sai | Lỗi nghiêm trọng |
|---|---|---|---|---|---|---|
| DeepSeek Harness | 60/60 | 100% | 94,0–100% | 55 giây | 0 | 0 |
| Claude Code | 59/60 | 98,3% | 91,1–99,7% | 112 giây | 1 | 0 |
| Claude Code (sandbox) | 57/60 | 95,0% | 86,3–98,3% | 113 giây | 2 | 0 |
| NexusAgent sau sửa | 57/60 | 95,0% | 86,3–98,3% | 193 giây | 2 | 0 |
| NexusAgent trước sửa (Phase 28) | 38/60 | 63,3% | 50,7–74,4% | 133 giây | 0 | 0 |

Kiểm định McNemar chính xác: sau sửa so với trước sửa p < 0,001 (22 tác vụ chỉ bản sau đạt, 3 chỉ bản trước đạt). So với DeepSeek Harness p = 0,25, với Claude Code p = 0,5, với Claude Code sandbox p = 1,0: không khác biệt có ý nghĩa thống kê, nhưng cũng chưa chứng minh là ngang nhau.

NexusAgent sau sửa còn rớt: `fix-021-config-merge-isolation`, `impl-008-ini-parser`, `impl-021-trie-autocomplete` (nguyên nhân chưa được phân tích).

Đọc kèm:
- Số liệu ghép từ hai lần chạy: 52 tác vụ chạy trên bản trước các sửa về vòng đời container, 8 tác vụ cuối (`impl-023` đến `impl-030`) chạy lại sau khi sửa. Hai bản khác nhau ở phần dừng sớm khi đã kiểm chứng và quản lý container, không khác ở logic kiểm chứng.
- Cải thiện được đo trên chính tập tác vụ đã dùng để tìm lỗi, nên có thể lạc quan. Cần tập mới chưa từng thấy.
- NexusAgent vẫn chậm hơn nhiều (trung vị 193 giây so với 55 giây).
- Lần chạy đầu của 8 tác vụ cuối chết vì lỗi hạ tầng: hơn 200 container sandbox không bao giờ được dọn làm Docker nghẽn. Đã sửa bằng cách trả container khi node xong, giới hạn số node chạy đồng thời, quét container mồ côi và tự thử lại. Sau sửa, số container tối đa 2 cùng lúc và về 0 khi xong. Một lỗi hồi quy do chính bản sửa gây ra (file giải pháp không được xuất ra nhưng run vẫn báo hoàn thành) đã được phát hiện qua benchmark và sửa; hiện run sẽ thất bại rõ ràng nếu không xuất được file.

### Đính chính sau khi phân tích 3 tác vụ còn rớt

- `impl-021-trie-autocomplete`: **không phải lỗi của agent.** Lời giải qua 12/12 test ẩn khi chấm lại. Bộ chấm ghi `FAIL 0/0` vì không chạy ra dòng "Ran N tests" (Docker đang nghẽn lúc chấm). Đã sửa `bench/grade.py`: không có dòng đó thì ghi `INFRA`, không ghi `FAIL`. Chấm lại: PASS. NexusAgent là **58/60 (96,7%)**, không phải 57/60.
- `impl-008-ini-parser`: lần đầu agent dừng với `BLOCKED` ("code did not run cleanly and no tests exist"), không giao file nào. Chạy lại một lần (`diag1`): PASS nhưng mất 505 giây. Lỗi không ổn định, chưa thấy dấu hiệu thiếu công cụ.
- `fix-021-config-merge-isolation`: lỗi logic thật. Khi khóa chưa có trong `base`, `deep_merge` sao chép nguyên dict override nên các giá trị `None` lồng bên trong không bị loại, trái với docstring ("cũng áp dụng cho dict override lồng nhau"). Agent báo DONE nhưng test tự viết không phủ trường hợp này.
- Kết luận: cả 3 trường hợp đều chưa chứng minh được "thiếu công cụ repo" là nguyên nhân. Bộ 60 tác vụ toàn file nhỏ nên cũng không đo được năng lực đó.

## Giai đoạn 30: tác vụ nhiều file (thư mục con)

Bộ `repo-001..004` là bốn package nhiều module, mỗi tác vụ có 3-4 lỗi nằm ở các file khác nhau (`ledger`, `textpipe`, `jobplan`, `router`).

**Lỗi của bộ đo đã làm sai các lượt đo trước (seq2-seq4).** Backend từ chối mọi tên file có đường dẫn ("Sandbox input filenames must not contain paths"), và adapter chỉ gửi file ở thư mục gốc. NexusAgent nhận một sandbox thiếu package, trả về "completed" mà không đổi file nào (số test đạt y hệt starter) và bị tính 0/4. Kết quả đó phản ánh giới hạn đầu vào, không phải năng lực của agent. Đã sửa cả hai phía: compiler nhận đường dẫn tương đối (tối đa 8 cấp, không `..`, không tuyệt đối), bộ kiểm chứng chạy được test nằm trong thư mục con, adapter gửi và tải về đệ quy.

**Một test ẩn mơ hồ đã bị sửa sau khi thấy kết quả.** `repo-001` đòi `to_cents("3.100") == 310` trong khi docstring nói hơn hai chữ số thập phân là `ValueError`. Cách đọc của agent hợp lệ, nên khẳng định đó bị bỏ và mọi lượt của repo-001 được chấm lại theo cùng một test (Claude Code và NexusAgent từ FAIL thành PASS, DeepSeek Harness vẫn FAIL).

| Hệ thống | repo-001 | repo-002 | repo-003 | repo-004 | Đạt | Thời gian mỗi tác vụ |
|---|---|---|---|---|---|---|
| NexusAgent (seq5) | PASS | PASS | PASS | PASS | **4/4** | 96-135 giây |
| Claude Code (seq3) | PASS | PASS | PASS | PASS | 4/4 | 377-812 giây |
| DeepSeek Harness (seq3) | FAIL | PASS | PASS | PASS | 3/4 | 98-442 giây |

Chi phí được tính: NexusAgent 0,124 USD, DeepSeek Harness 0,171 USD, Claude Code 0,085 USD cho 4 tác vụ.

**Cách đọc.** Mỗi ô chỉ một lần chạy, bốn tác vụ do chính chúng tôi viết, và lượt NexusAgent được đo sau khi sửa lỗi bộ đo và đường gọi model (khóa 401) dựa trên các tác vụ này, nên con số có xu hướng lạc quan. Điều đáng tin: khoảng cách 0/4 trước đó là do giao diện đầu vào, không phải do thiếu công cụ sửa file, và giả thuyết "cần `read_file`/`edit_file`/`grep`/`glob`" chưa có bằng chứng ủng hộ. Việc cần làm tiếp là chạy lặp 3 lần và thêm tác vụ mới chưa từng dùng để chỉnh sửa.

## Giai đoạn 31: sáu tác vụ nhiều file mới, chạy lặp 3 lần

Sáu tác vụ mới (`repo-005-stock`, `repo-006-calendar`, `repo-007-resilient`, `repo-008-acl`, `repo-009-mdlite`, `repo-010-pager`), mỗi tác vụ là một package 3-4 module với 3-5 lỗi nằm ở các file khác nhau. Chưa hệ thống nào từng thấy chúng và không sửa gì sau khi chạy. Trước khi chạy, `bench.validate` bắt được một giá trị sai trong test ẩn của chúng tôi và việc rà soát tìm ra một khẳng định mơ hồ (coi `True` là số nguyên); cả hai đã sửa trước khi có hệ thống nào chạy. Mỗi hệ thống chạy 6 tác vụ x 3 lần = 18 lượt, giới hạn 15 phút mỗi lượt.

| Hệ thống | Đạt | Wilson 95% | Tuyên bố sai | Trung vị | Lâu nhất |
|---|---|---|---|---|---|
| Claude Code | 17/18 (94,4%) | 74,2-99,0% | 1 | 261 giây | 586 giây |
| DeepSeek Harness | 16/18 (88,9%) | 67,2-96,9% | 2 | 125 giây | 243 giây |
| NexusAgent | 15/18 (83,3%) | 60,8-94,2% | 3 | 115 giây | 225 giây |

Không có lượt INFRA, TIMEOUT hay SEVERE.

Kiểm định cặp (McNemar chính xác, ghép theo tác vụ và lần chạy): NexusAgent so với DeepSeek Harness p = 1,0 (1 so với 2 lượt chỉ một bên đạt); NexusAgent so với Claude Code p = 0,5 (0 so với 2); DeepSeek Harness so với Claude Code p = 1,0. Không có khác biệt có ý nghĩa thống kê, và với 18 lượt cũng không đủ để chứng minh là ngang nhau.

Theo tác vụ (PPP là đạt cả 3 lần): `cal`, `resilient`, `acl`, `pager` đạt 3/3 ở cả ba hệ thống. `stock`: NexusAgent PPF, hai hệ thống kia PPP. `mdlite`: NexusAgent FPF, DeepSeek Harness PFF, Claude Code PPF; đây là tác vụ khó với cả ba.

Nguyên nhân ba lần rớt của NexusAgent (đã đọc từng workspace):
- `mdlite` (2 lần): xử lý `*...*` trước khi nhận dạng code span, nên `` `b*` `` không thành `<code>`, trái với đề. Cả hai lần cùng một lỗi và agent không tự viết test cho trường hợp đó.
- `stock` (1 lần): `orders.py` dùng `OutOfStock` mà không import (`NameError`). Test đi kèm không chạy nhánh đó nên bộ kiểm chứng vẫn báo hợp lệ. Một kiểm tra tĩnh về tên chưa định nghĩa sẽ bắt được lỗi này mà không tốn thêm lượt gọi model.

**Cách đọc.** Ba hệ thống chạy song song trên cùng một cổng API, nên thời gian chỉ mang tính tham khảo (độ chính xác là số đo chính). Chi phí không tách riêng được vì billing đo chung. 18 lượt mỗi hệ thống là cỡ mẫu nhỏ: khoảng tin cậy chồng lấn nhiều. Các tác vụ do chúng tôi viết nên có thể thiên về kiểu lỗi mà chúng tôi hình dung ra. Kết luận có thể nói: trên bộ này NexusAgent ở cùng tầm với hai đối thủ, nhanh hơn Claude Code, và tỉ lệ tuyên bố sai cao hơn (3/18 so với 2/18 và 1/18, chưa có ý nghĩa thống kê).

## Tái tạo

```bash
cd benchmarks/code-tasks
python3 -m bench.validate          # 60 tác vụ hợp lệ
python3 -m bench.selftest          # agent giả: PASS / SEVERE / FAIL / báo sai
set -a; . ./.env.bench; set +a     # BENCH_API_KEY, BENCH_MODEL, BENCH_OPENAI_BASE_URL, BENCH_ANTHROPIC_BASE_URL
python3 -m bench.run --system dsh --run-id full1 --timeout 600 --workers 3 --budget-usd 3
python3 -m bench.regrade --run-id full1
python3 -m bench.report --run-id full1
```

Hệ thống hỗ trợ: `claude_code`, `claude_code_sbx`, `dsh`, `nexus`, `nexus_plain`. Cần cài dsh riêng (`@deepseek-ai/dsh@0.2.1-rc.5`, file vá nằm ở `dsh/cordis.patch.yml`) và dựng stack NexusAgent (`docker compose -p nexus-bench up -d`). Dữ liệu thô nằm ở `results/full1/` (không commit). Khoá API nằm trong `.env.bench` (không commit).
