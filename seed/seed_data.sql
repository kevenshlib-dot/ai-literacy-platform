--
-- PostgreSQL database dump
--

\restrict Ti2eXBmPxKI7BcqHJfPO7A0tT9G0qPaYXExznP5BuiSrCMI3wTbdpTIhCt1X95h

-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: roles; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.roles VALUES ('f55fa1a5-ff97-4d94-99aa-7b293f203f88', 'admin', 'admin');
INSERT INTO public.roles VALUES ('ee5d42bc-b073-46cf-bc3e-2c5b21d6da98', 'organizer', 'organizer');
INSERT INTO public.roles VALUES ('8389c44a-ee83-4ad0-9cd7-68e1c1a6f01a', 'examinee', 'examinee');
INSERT INTO public.roles VALUES ('e742af2c-9f07-459c-a5b8-f11bbcc961f3', 'reviewer', 'reviewer');


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.users VALUES ('f153e781-dca0-46af-8430-a62aa9b59a9b', 'admin', 'admin@example.com', '$2b$12$LpWHK4F/9.Zf96Bwh0NcTO4d7j.1hyXrXg4piQ6WbF5gfxU3V8xVa', '系统管理员', NULL, NULL, true, 'f55fa1a5-ff97-4d94-99aa-7b293f203f88', '2026-04-13 12:27:59.109999+00', '2026-04-13 12:27:59.110003+00', false, NULL, NULL, true);
INSERT INTO public.users VALUES ('8dd826c5-7608-4435-8163-af305886ce73', 'keven', 'kevenshlib@gmail.com', '$2b$12$.lj7fO7u5G78QSyzRW0VaOLdVC3loLZQ1F5PPsJNXfb8j3Y1HOJG2', 'Keven', '', '', true, 'f55fa1a5-ff97-4d94-99aa-7b293f203f88', '2026-04-13 12:43:17.119012+00', '2026-04-13 12:43:17.119016+00', false, NULL, NULL, true);


--
-- Data for Name: papers; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.papers VALUES ('e1e865d7-aa58-40ed-a579-821e01727fc6', 'AI素养判断题', '', 'archived', 50, NULL, 1, 'null', NULL, 0, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 12:29:28.595856+00', '2026-04-13 12:31:03.860968+00');
INSERT INTO public.papers VALUES ('78857fa1-7749-49d1-8212-960cafa5c376', 'AI素养判断题', '', 'archived', 50, NULL, 1, 'null', NULL, 0, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 12:29:10.537988+00', '2026-04-13 12:31:10.778938+00');
INSERT INTO public.papers VALUES ('f39b7deb-227c-4835-a893-f7ea5958e164', 'AI素养判断题', '', 'published', 50, NULL, 1, 'null', NULL, 1, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 14:56:45.464576+00', '2026-04-13 14:56:57.66564+00');
INSERT INTO public.papers VALUES ('3ce99078-b7df-4ab9-801a-138ba9a883eb', 'AI素养课后测试', '', 'archived', 50, NULL, 1, 'null', NULL, 1, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 12:31:48.330592+00', '2026-04-13 12:38:01.584045+00');
INSERT INTO public.papers VALUES ('fa8f78cc-ca63-409a-93f6-19225c7224fa', 'AI素养判断题', '', 'archived', 50, NULL, 1, 'null', NULL, 1, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 12:41:31.492501+00', '2026-04-13 12:57:24.553781+00');
INSERT INTO public.papers VALUES ('d14dc73f-fd3a-44e9-b416-55827067ff1c', 'AI素养课后测试', '请判断以下每道题的表述是否正确，在题号后的括号内填写“✓”（正确）或“✗”（错误）。共 10 题。', 'archived', 50, NULL, 1, 'null', NULL, 1, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 13:11:25.327535+00', '2026-04-13 13:32:42.038362+00');
INSERT INTO public.papers VALUES ('73f4246b-c573-4aba-939f-d532a353cddb', 'AI素养课后测试', '', 'archived', 50, NULL, 1, 'null', NULL, 1, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 13:51:06.262517+00', '2026-04-13 13:57:34.480813+00');
INSERT INTO public.papers VALUES ('c2706a24-6811-4123-ab7b-60051b99c9d2', 'AI素养课前测试（附答案及解析）', '', 'archived', 5, NULL, 1, 'null', NULL, 0, '8dd826c5-7608-4435-8163-af305886ce73', '2026-04-13 14:05:32.207651+00', '2026-04-13 14:09:14.200618+00');
INSERT INTO public.papers VALUES ('9523172e-f342-4229-8ea2-3afa97eccd0b', 'AI素养课前测试', '请判断以下每道题的表述是否正确，在题号后的括号内填写“✓”（正确）或“✗”（错误）。共 10 题。', 'archived', 50, NULL, 1, 'null', NULL, 1, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 13:34:13.808303+00', '2026-04-13 14:20:00.499399+00');
INSERT INTO public.papers VALUES ('05d32cd8-92c4-4f81-a996-b19028a91734', 'AI素养课后测试', '请判断以下每道题的表述是否正确，在题号后的括号内填写“✓”（正确）或“✗”（错误）。共 10 题。', 'archived', 50, NULL, 1, 'null', NULL, 1, '8dd826c5-7608-4435-8163-af305886ce73', '2026-04-13 14:01:14.606627+00', '2026-04-13 14:20:02.354955+00');
INSERT INTO public.papers VALUES ('84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'AI素养课后测试', '', 'archived', 50, NULL, 1, 'null', NULL, 1, '8dd826c5-7608-4435-8163-af305886ce73', '2026-04-13 14:47:06.587365+00', '2026-04-13 14:48:59.581378+00');
INSERT INTO public.papers VALUES ('24e05b5f-f682-45cc-85f6-48353f3c3f19', 'AI素养判断题', '', 'published', 50, NULL, 1, 'null', NULL, 1, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 14:52:52.097034+00', '2026-04-13 14:55:31.182963+00');


--
-- Data for Name: exams; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.exams VALUES ('623faf27-10c4-48e6-bfb1-3a8b673186be', 'AI素养课后测试', '', 'closed', 50, NULL, NULL, 0, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 12:32:30.870017+00', '2026-04-13 12:38:01.586551+00', '3ce99078-b7df-4ab9-801a-138ba9a883eb');
INSERT INTO public.exams VALUES ('a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', 'AI素养课后测试', '', 'closed', 50, NULL, NULL, 0, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 13:51:13.712304+00', '2026-04-13 13:57:34.482537+00', '73f4246b-c573-4aba-939f-d532a353cddb');
INSERT INTO public.exams VALUES ('a46b9d4c-633c-46f4-ae8e-f8db6b865112', 'AI素养课后测试', '', 'closed', 50, NULL, NULL, 0, NULL, '8dd826c5-7608-4435-8163-af305886ce73', '2026-04-13 14:47:21.152827+00', '2026-04-13 14:48:59.58468+00', '84c6b2ec-2c09-430c-aea8-4660aaa6304a');
INSERT INTO public.exams VALUES ('dbea20ee-62ab-410c-a034-ec54773ba2a0', 'AI素养判断题', '', 'published', 50, NULL, NULL, 0, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 14:55:31.169857+00', '2026-04-13 14:55:31.169866+00', '24e05b5f-f682-45cc-85f6-48353f3c3f19');
INSERT INTO public.exams VALUES ('a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', 'AI素养判断题前', '', 'published', 50, NULL, NULL, 0, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', '2026-04-13 14:56:57.661231+00', '2026-04-13 14:57:25.229064+00', 'f39b7deb-227c-4835-a893-f7ea5958e164');


--
-- Data for Name: questions; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.questions VALUES ('8882f966-8ee5-4d50-9630-0814be6876dd', 'true_false', '(      )  大语言模型在回答用户问题时，其工作方式类似于从已学习的资料中检索相关段落并整理输出。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.554143+00', '2026-04-13 12:29:10.554146+00');
INSERT INTO public.questions VALUES ('81c9880d-0ac8-41b7-86ef-2b8479f001a3', 'true_false', '(      )  当AI的回答中附带了具体的参考文献信息（如作者、年份、期刊名），这些引用一般是真实存在的。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.557109+00', '2026-04-13 12:29:10.55711+00');
INSERT INTO public.questions VALUES ('d1659494-7f7c-4121-81f6-53ff5eed7edd', 'true_false', '(      )  同一个问题在不同对话中提问同一个AI模型，得到的回答可能存在实质性差异甚至互相矛盾。', '{"F": "错误", "T": "正确"}', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.55848+00', '2026-04-13 12:29:10.558481+00');
INSERT INTO public.questions VALUES ('e16ea688-f143-443c-ba3c-1863ba12c5d1', 'true_false', '(      )  开源的AI模型通常意味着其训练数据的来源和构成也是公开透明的。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.559926+00', '2026-04-13 12:29:10.559927+00');
INSERT INTO public.questions VALUES ('c888434f-dd7c-4bce-abaa-3cafa2134eca', 'true_false', '(      )  仅仅改变提示词（prompt）中几个词的表述方式，就可能显著改变AI回答的质量和方向。', '{"F": "错误", "T": "正确"}', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.56142+00', '2026-04-13 12:29:10.561421+00');
INSERT INTO public.questions VALUES ('51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 'true_false', '(      )  目前主流的AI文本检测工具已经能够比较可靠地区分AI生成的文本与人类写作。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.562692+00', '2026-04-13 12:29:10.562693+00');
INSERT INTO public.questions VALUES ('88ba4572-ce6c-4f3a-9296-042b112392d7', 'true_false', '(      )  AI模型在处理涉及不同文化背景的内容时，可能表现出系统性的认知偏差。', '{"F": "错误", "T": "正确"}', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.563912+00', '2026-04-13 12:29:10.563913+00');
INSERT INTO public.questions VALUES ('ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 'true_false', '(      )  当AI表示“我对这个问题不太有把握”时，说明它确实感知到了自身知识的局限。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.565069+00', '2026-04-13 12:29:10.56507+00');
INSERT INTO public.questions VALUES ('cf07a686-a2dd-4819-9827-9e129e58fac3', 'true_false', '(      )  在多数国家现行法律框架下，纯粹由AI生成的作品不享有版权保护。', '{"F": "错误", "T": "正确"}', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.566273+00', '2026-04-13 12:29:10.566274+00');
INSERT INTO public.questions VALUES ('9739d9f0-09c3-423f-b51e-274ac45e0d8c', 'true_false', '(      )  模型参数量越大，AI回答的准确性和可靠性通常就越高。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:29:10.567443+00', '2026-04-13 12:29:10.567444+00');
INSERT INTO public.questions VALUES ('f98dd36c-6152-49ca-95b8-dc8ff8254bbc', 'short_answer', '(      )  AI辅助质性研究编码比人工编码更客观，因为它排除了研究者个人倾向的干扰。', 'null', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.339555+00', '2026-04-13 12:31:48.339566+00');
INSERT INTO public.questions VALUES ('ff3a145b-6bb4-40b3-857a-bebd70799c4c', 'short_answer', '(      )  大语言模型有时会以非常笃定的语气给出完全错误的回答，且回答的格式和逻辑看起来十分完整。', 'null', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.345879+00', '2026-04-13 12:31:48.345886+00');
INSERT INTO public.questions VALUES ('63f41632-89e4-496b-be83-847b3af49755', 'short_answer', '(      )  用AI翻译的学术文本，只要读起来通顺流畅，一般不会有严重的语义偏差。', 'null', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.350028+00', '2026-04-13 12:31:48.350034+00');
INSERT INTO public.questions VALUES ('3438d275-a415-4685-9a70-f1df19cab9eb', 'short_answer', '(      )  对AI进行人类偏好对齐训练（如RLHF），有时反而会让模型倾向于给出讨好用户但不够深入的回答。', 'null', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.354195+00', '2026-04-13 12:31:48.3542+00');
INSERT INTO public.questions VALUES ('60902f5b-3045-46cc-898f-c9e91493f323', 'short_answer', '(      )  Transformer架构之所以在自然语言处理领域表现突出，核心在于它模拟了人类大脑神经元的协作方式。', 'null', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.357944+00', '2026-04-13 12:31:48.357948+00');
INSERT INTO public.questions VALUES ('c4c69d6e-a6d5-489f-acd4-5bace6445708', 'short_answer', '(      )  大语言模型的训练数据如果包含某部学术专著，它就能比较准确地引用其中的具体段落或观点。', 'null', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.362483+00', '2026-04-13 12:31:48.36249+00');
INSERT INTO public.questions VALUES ('a3cec998-adf9-410f-a0da-cc4ba790fbff', 'short_answer', '(      )  将含有个人信息的研究数据上传到免费AI平台进行分析，通常不会引发数据安全方面的担忧。', 'null', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.366638+00', '2026-04-13 12:31:48.366643+00');
INSERT INTO public.questions VALUES ('b5410655-21dd-4152-ac38-87eb7ecbadbf', 'short_answer', '(      )  用相同数据训练出的不同架构的AI模型，对同一份质性材料可能给出差异很大的分析结论。', 'null', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.370578+00', '2026-04-13 12:31:48.370584+00');
INSERT INTO public.questions VALUES ('aabb6e1a-400d-4a74-b2ca-3b6a05678133', 'short_answer', '(      )  在学术论文写作中使用了AI辅助，只要经过充分的人工审校和编辑，就不必在论文中专门披露。', 'null', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.374524+00', '2026-04-13 12:31:48.374531+00');
INSERT INTO public.questions VALUES ('1ff73c36-034d-4ae8-95d1-60a456f5b458', 'short_answer', '(      )  大语言模型在某些看似需要“推理”的任务中表现出色，可能只是因为训练数据中包含了大量类似的问答模式。', 'null', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 12:31:48.378293+00', '2026-04-13 12:31:48.378297+00');
INSERT INTO public.questions VALUES ('643378cf-27dd-4cde-a8f2-657d9449359d', 'true_false', '(      )  AI辅助质性研究编码比人工编码更客观，因为它排除了研究者个人倾向的干扰。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.33057+00', '2026-04-13 13:11:25.330574+00');
INSERT INTO public.questions VALUES ('3b16303a-0f49-405d-b30f-bbd2752f5be1', 'true_false', '(      )  大语言模型有时会以非常笃定的语气给出完全错误的回答，且回答的格式和逻辑看起来十分完整。', '{"F": "错误", "T": "正确"}', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.333877+00', '2026-04-13 13:11:25.333881+00');
INSERT INTO public.questions VALUES ('3da97a34-1d05-456a-8859-083e82fb9395', 'true_false', '(      )  用AI翻译的学术文本，只要读起来通顺流畅，一般不会有严重的语义偏差。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.336138+00', '2026-04-13 13:11:25.33614+00');
INSERT INTO public.questions VALUES ('61f9633f-9b12-4746-aa9e-11740ff4c191', 'true_false', '(      )  对AI进行人类偏好对齐训练（如RLHF），有时反而会让模型倾向于给出讨好用户但不够深入的回答。', '{"F": "错误", "T": "正确"}', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.338718+00', '2026-04-13 13:11:25.33872+00');
INSERT INTO public.questions VALUES ('09046eee-568e-4fbc-bcd4-6a49d7b32f87', 'true_false', '(      )  Transformer架构之所以在自然语言处理领域表现突出，核心在于它模拟了人类大脑神经元的协作方式。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.340798+00', '2026-04-13 13:11:25.3408+00');
INSERT INTO public.questions VALUES ('ddb63565-cb08-48fe-8ec6-1687d03917f3', 'true_false', '(      )  大语言模型的训练数据如果包含某部学术专著，它就能比较准确地引用其中的具体段落或观点。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.343284+00', '2026-04-13 13:11:25.343286+00');
INSERT INTO public.questions VALUES ('42fb55e0-fdce-4bf8-9d7f-ad6db798652a', 'true_false', '(      )  将含有个人信息的研究数据上传到免费AI平台进行分析，通常不会引发数据安全方面的担忧。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.345588+00', '2026-04-13 13:11:25.34559+00');
INSERT INTO public.questions VALUES ('31699b07-0acd-4fc3-8713-46579dd9f447', 'true_false', '(      )  用相同数据训练出的不同架构的AI模型，对同一份质性材料可能给出差异很大的分析结论。', '{"F": "错误", "T": "正确"}', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.348022+00', '2026-04-13 13:11:25.348024+00');
INSERT INTO public.questions VALUES ('2a330872-43ab-4ac7-9226-b5a67341a6e9', 'true_false', '(      )  在学术论文写作中使用了AI辅助，只要经过充分的人工审校和编辑，就不必在论文中专门披露。', '{"F": "错误", "T": "正确"}', 'F', '错误', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.350309+00', '2026-04-13 13:11:25.350311+00');
INSERT INTO public.questions VALUES ('421fe593-0d22-4265-94b3-e883098f2804', 'true_false', '(      )  大语言模型在某些看似需要“推理”的任务中表现出色，可能只是因为训练数据中包含了大量类似的问答模式。', '{"F": "错误", "T": "正确"}', 'T', '正确', NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, 'f153e781-dca0-46af-8430-a62aa9b59a9b', NULL, '2026-04-13 13:11:25.352739+00', '2026-04-13 13:11:25.352742+00');
INSERT INTO public.questions VALUES ('0f4a4f50-5f24-482d-9f27-26ef39464b08', 'short_answer', '( ✗ ) 大语言模型在回答用户问题时，其工作方式类似于从已学习的资料中检索相关段落并整理输出。', 'null', '', NULL, NULL, 3, NULL, 'null', NULL, NULL, NULL, 'draft', 0, NULL, NULL, NULL, NULL, '8dd826c5-7608-4435-8163-af305886ce73', NULL, '2026-04-13 14:08:33.572018+00', '2026-04-13 14:08:33.572029+00');


--
-- Data for Name: exam_questions; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.exam_questions VALUES ('126db778-2b9c-478a-8acd-b57a42108080', '623faf27-10c4-48e6-bfb1-3a8b673186be', 'f98dd36c-6152-49ca-95b8-dc8ff8254bbc', 1, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('58c1a04a-28db-4734-aa4d-1c7551fc270e', '623faf27-10c4-48e6-bfb1-3a8b673186be', 'ff3a145b-6bb4-40b3-857a-bebd70799c4c', 2, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('fabe37a6-4f85-42f7-88f9-b3704b9e6a2a', '623faf27-10c4-48e6-bfb1-3a8b673186be', '63f41632-89e4-496b-be83-847b3af49755', 3, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('38bbf93a-b9d9-4ab7-8eee-6decfbcc95d7', '623faf27-10c4-48e6-bfb1-3a8b673186be', '3438d275-a415-4685-9a70-f1df19cab9eb', 4, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('4a99b6c4-3761-402d-b2a9-9143cb91c268', '623faf27-10c4-48e6-bfb1-3a8b673186be', '60902f5b-3045-46cc-898f-c9e91493f323', 5, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('3201dae1-aa56-4dbe-9147-dfc132e645bd', '623faf27-10c4-48e6-bfb1-3a8b673186be', 'c4c69d6e-a6d5-489f-acd4-5bace6445708', 6, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('ab2295ee-fda8-45fd-bf28-7bd642f90b80', '623faf27-10c4-48e6-bfb1-3a8b673186be', 'a3cec998-adf9-410f-a0da-cc4ba790fbff', 7, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('b4e0a0cf-7548-41fc-8ae6-a8677153a5b3', '623faf27-10c4-48e6-bfb1-3a8b673186be', 'b5410655-21dd-4152-ac38-87eb7ecbadbf', 8, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('2f165dd1-655d-44fb-8486-afb9540bcb3d', '623faf27-10c4-48e6-bfb1-3a8b673186be', 'aabb6e1a-400d-4a74-b2ca-3b6a05678133', 9, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('a55610f5-f0f7-40e4-a91d-89b8d65b68e8', '623faf27-10c4-48e6-bfb1-3a8b673186be', '1ff73c36-034d-4ae8-95d1-60a456f5b458', 10, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('f6d98122-9a24-4478-8d4e-62e8d3446835', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', 'f98dd36c-6152-49ca-95b8-dc8ff8254bbc', 1, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('a98b63ce-1e79-4849-9ddd-e769afa18483', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', 'ff3a145b-6bb4-40b3-857a-bebd70799c4c', 2, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('861cf82d-3acd-4836-a5c3-c3138339c79e', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', '63f41632-89e4-496b-be83-847b3af49755', 3, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('bc3bd92c-0301-4bd3-9bd7-a9585a8a8701', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', '3438d275-a415-4685-9a70-f1df19cab9eb', 4, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('8add2e0d-e8fd-4ad1-9f3e-1e78015b0951', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', '60902f5b-3045-46cc-898f-c9e91493f323', 5, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('99082daa-8af5-48dd-a6fd-2f79f159d708', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', 'c4c69d6e-a6d5-489f-acd4-5bace6445708', 6, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('686285c2-e174-409f-bd50-8cf7089f6ce0', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', 'a3cec998-adf9-410f-a0da-cc4ba790fbff', 7, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('45ad6aab-8a68-4654-8b73-b1bde23a632b', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', 'b5410655-21dd-4152-ac38-87eb7ecbadbf', 8, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('cc73cb6f-227b-42fb-95c5-d5656a939db3', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', 'aabb6e1a-400d-4a74-b2ca-3b6a05678133', 9, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('12a12dbb-6350-44f3-9295-4cca79c0cac2', 'a7ad0e55-6c6a-4dc7-a9ea-f6d244f0fc1c', '1ff73c36-034d-4ae8-95d1-60a456f5b458', 10, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('4829c09e-d421-43ce-a713-ea7d1b5bf8ff', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', 'f98dd36c-6152-49ca-95b8-dc8ff8254bbc', 1, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('4518fdce-ff05-40f6-a84d-898f19e1dee3', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', 'ff3a145b-6bb4-40b3-857a-bebd70799c4c', 2, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('fd1aa756-f06b-43fd-a816-d2aab9b61aef', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', '63f41632-89e4-496b-be83-847b3af49755', 3, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('3db4bdf3-a1a1-4a43-8103-d62fbc0eaea0', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', '3438d275-a415-4685-9a70-f1df19cab9eb', 4, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('55127c00-8bca-4132-b282-38f9d67f704a', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', '60902f5b-3045-46cc-898f-c9e91493f323', 5, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('54da7ef0-2c89-48f7-b5d9-ce475246db49', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', 'c4c69d6e-a6d5-489f-acd4-5bace6445708', 6, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('973dcb38-1eac-4fab-a2f5-65949f6d6a13', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', 'a3cec998-adf9-410f-a0da-cc4ba790fbff', 7, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('76819913-4bb8-4dfa-b540-ed3066cfe36b', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', 'b5410655-21dd-4152-ac38-87eb7ecbadbf', 8, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('6579c8a9-8a7d-4ac0-972d-e014febd9420', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', 'aabb6e1a-400d-4a74-b2ca-3b6a05678133', 9, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('c4f4475e-bd16-43ef-acf1-05d0c0e37f03', 'a46b9d4c-633c-46f4-ae8e-f8db6b865112', '1ff73c36-034d-4ae8-95d1-60a456f5b458', 10, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('8aca8bb4-1bd0-4160-9c2d-2e25c8c2898e', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', '8882f966-8ee5-4d50-9630-0814be6876dd', 1, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('94cacf9d-d740-4202-a11c-3a5e4f932dd4', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', '81c9880d-0ac8-41b7-86ef-2b8479f001a3', 2, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('d9eec142-86d2-4a2b-9501-d3e720b7def9', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', 'd1659494-7f7c-4121-81f6-53ff5eed7edd', 3, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('79ed8229-26e8-49ce-aec6-a514146965e0', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', 'e16ea688-f143-443c-ba3c-1863ba12c5d1', 4, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('248b71e2-194d-4a92-98ef-b6d9281d8fc4', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', 'c888434f-dd7c-4bce-abaa-3cafa2134eca', 5, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('48c55508-a02a-49cb-8476-7006af6ebfbb', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', '51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 6, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('fc428265-64bd-428e-8362-f4ff9c45d4bd', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', '88ba4572-ce6c-4f3a-9296-042b112392d7', 7, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('18b6eb26-6cc5-463c-a6da-824fac16b2ec', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', 'ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 8, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('17ea6d2e-4f6c-4e7b-a626-1d9e21350e45', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', 'cf07a686-a2dd-4819-9827-9e129e58fac3', 9, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('7d6dc753-7efc-44b0-b3f0-465da9f0100c', 'dbea20ee-62ab-410c-a034-ec54773ba2a0', '9739d9f0-09c3-423f-b51e-274ac45e0d8c', 10, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('733dced4-69d2-4758-a86f-09a01c6d2e77', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', '8882f966-8ee5-4d50-9630-0814be6876dd', 1, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('fce217e9-b6f1-4975-91d4-c4cd8102b305', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', '81c9880d-0ac8-41b7-86ef-2b8479f001a3', 2, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('7310a61a-5f96-4ff1-8bec-b575eb3b91e9', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', 'd1659494-7f7c-4121-81f6-53ff5eed7edd', 3, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('cf33c03b-894d-4a75-a9ac-4b57c8e6815e', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', 'e16ea688-f143-443c-ba3c-1863ba12c5d1', 4, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('e363b49f-e99b-467a-a245-06a1a17732d2', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', 'c888434f-dd7c-4bce-abaa-3cafa2134eca', 5, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('374e4b39-515c-4797-889a-011205e8a648', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', '51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 6, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('d5571b04-6831-4fe1-a6f6-23ae1db00a6e', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', '88ba4572-ce6c-4f3a-9296-042b112392d7', 7, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('18e94fb9-4d83-4000-8f0e-9ff1d4d132bd', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', 'ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 8, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('d383896d-a684-4363-bbb4-31a41f3a4859', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', 'cf07a686-a2dd-4819-9827-9e129e58fac3', 9, 5, NULL, NULL);
INSERT INTO public.exam_questions VALUES ('1df0c86b-665e-4785-a212-e8401200b0b1', 'a4e6e4ba-e9ca-4572-a25e-003a7c4ad6fb', '9739d9f0-09c3-423f-b51e-274ac45e0d8c', 10, 5, NULL, NULL);


--
-- Data for Name: paper_sections; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.paper_sections VALUES ('a3c501df-3bad-422a-b436-5eb93d68c5b5', '78857fa1-7749-49d1-8212-960cafa5c376', 'AI素养判断题', NULL, 1, '{"count": null, "total": null, "score_per_question": 5.0}');
INSERT INTO public.paper_sections VALUES ('c7af8c3a-60dd-4e73-b478-d13bdcc2b403', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'AI素养判断题', NULL, 1, '{"count": null, "total": null, "score_per_question": 5.0}');
INSERT INTO public.paper_sections VALUES ('ec247d58-5813-4257-a241-f8ba141663e9', '3ce99078-b7df-4ab9-801a-138ba9a883eb', '简答题', NULL, 1, 'null');
INSERT INTO public.paper_sections VALUES ('fae2f60a-5024-42bb-9886-ec082d5d8fc3', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'AI素养判断题', NULL, 1, '{"count": null, "total": null, "score_per_question": 5.0}');
INSERT INTO public.paper_sections VALUES ('3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '判断题', '判断题（每题 5 分，共 50 分）', 1, '{"count": null, "total": 50, "score_per_question": 5}');
INSERT INTO public.paper_sections VALUES ('d52bd12f-0c54-4083-acbf-708ef29d6a75', '9523172e-f342-4229-8ea2-3afa97eccd0b', '判断题', '判断题（每题 5 分，共 50 分）', 1, '{"count": null, "total": 50, "score_per_question": 5}');
INSERT INTO public.paper_sections VALUES ('6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', '73f4246b-c573-4aba-939f-d532a353cddb', '简答题', NULL, 1, 'null');
INSERT INTO public.paper_sections VALUES ('290ad277-ca62-4d2a-8653-b2e0974b8002', '05d32cd8-92c4-4f81-a996-b19028a91734', '判断题', '判断题（每题 5 分，共 50 分）', 1, '{"count": null, "total": 50, "score_per_question": 5}');
INSERT INTO public.paper_sections VALUES ('8f3d0649-9d23-4c4c-a17c-e38ee01b60e2', 'c2706a24-6811-4123-ab7b-60051b99c9d2', '简答题', NULL, 1, 'null');
INSERT INTO public.paper_sections VALUES ('edee95e8-9e2f-472e-b155-ddc8add706ae', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', '简答题', NULL, 1, 'null');
INSERT INTO public.paper_sections VALUES ('432c934e-93d8-4fa4-bfd7-22c090c69078', '24e05b5f-f682-45cc-85f6-48353f3c3f19', 'AI素养判断题', NULL, 1, '{"count": null, "total": null, "score_per_question": 5.0}');
INSERT INTO public.paper_sections VALUES ('7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', 'f39b7deb-227c-4835-a893-f7ea5958e164', 'AI素养判断题', NULL, 1, '{"count": null, "total": null, "score_per_question": 5}');


--
-- Data for Name: paper_questions; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.paper_questions VALUES ('e9eaac8d-7492-4ca9-8fa7-8762b02cafe1', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', '8882f966-8ee5-4d50-9630-0814be6876dd', 1, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('a7bd83a8-b5d5-4d88-adb3-e1bf791617f6', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', '81c9880d-0ac8-41b7-86ef-2b8479f001a3', 2, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('fd69a022-47a0-4364-9971-bf1e9dfed00f', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', 'd1659494-7f7c-4121-81f6-53ff5eed7edd', 3, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('6bbfcc8f-dd19-4829-bb35-6e3d0f72104b', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', 'e16ea688-f143-443c-ba3c-1863ba12c5d1', 4, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('1779d662-a7da-4336-b02c-ee4b6f0112f9', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', 'c888434f-dd7c-4bce-abaa-3cafa2134eca', 5, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('b018a71c-b4ba-4cc6-967d-9853f967058e', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', '51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 6, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('29bb8e9d-aaba-4190-bdce-18a9f4f9b7f0', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', '88ba4572-ce6c-4f3a-9296-042b112392d7', 7, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('eb4dc00a-e175-4f82-b0bb-56b665b2292f', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', 'ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 8, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('adcde00b-f91c-43eb-bb6e-1832aab5004d', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', 'cf07a686-a2dd-4819-9827-9e129e58fac3', 9, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('9ef8ca0d-9863-4630-b286-6fc2e8546ce8', '78857fa1-7749-49d1-8212-960cafa5c376', 'a3c501df-3bad-422a-b436-5eb93d68c5b5', '9739d9f0-09c3-423f-b51e-274ac45e0d8c', 10, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('532924f9-9c43-4368-8f2d-7fa279c39dc0', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', '8882f966-8ee5-4d50-9630-0814be6876dd', 1, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('e274d442-a2f0-44ef-9a68-ad0804efbe8a', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', '81c9880d-0ac8-41b7-86ef-2b8479f001a3', 2, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('2f311538-2a3a-48fb-83d3-6155ba64ea2a', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', 'd1659494-7f7c-4121-81f6-53ff5eed7edd', 3, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('2ec9bd04-dc74-499e-9f8d-6a5e47c7adc0', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', 'e16ea688-f143-443c-ba3c-1863ba12c5d1', 4, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('899e8c6b-eb9c-4e88-8d67-cd8850bcc574', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', 'c888434f-dd7c-4bce-abaa-3cafa2134eca', 5, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('d5bd913a-21db-4920-b5e6-dcb9c06fce96', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', '51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 6, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('dd5e3e5f-5b13-4490-9bf1-3204d3b1c604', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', '88ba4572-ce6c-4f3a-9296-042b112392d7', 7, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('0c1a3f80-f8f1-48ea-a250-a00b45fb5c10', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', 'ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 8, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('f9aeecf7-fe9a-4041-93ad-7fbcb0546932', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', 'cf07a686-a2dd-4819-9827-9e129e58fac3', 9, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('9ffb5333-3675-4e2d-b03d-a53296d592d5', 'e1e865d7-aa58-40ed-a579-821e01727fc6', 'c7af8c3a-60dd-4e73-b478-d13bdcc2b403', '9739d9f0-09c3-423f-b51e-274ac45e0d8c', 10, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('6b84dc0c-df4d-45b0-a247-db7582232252', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', 'f98dd36c-6152-49ca-95b8-dc8ff8254bbc', 1, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('c327a72d-eb63-4255-a66f-6f229286e84b', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', 'ff3a145b-6bb4-40b3-857a-bebd70799c4c', 2, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('0e423cf7-cd61-4342-938d-fa58ce6b61b4', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', '63f41632-89e4-496b-be83-847b3af49755', 3, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('997fe3c8-4695-4b25-a707-fad9e5c24b29', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', '3438d275-a415-4685-9a70-f1df19cab9eb', 4, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('ddd04274-0ab1-4866-86dd-70e03c60b1d4', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', '60902f5b-3045-46cc-898f-c9e91493f323', 5, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('892b4525-d0d0-4415-a257-4272465740ba', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', 'c4c69d6e-a6d5-489f-acd4-5bace6445708', 6, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('86ac61a2-985f-4b61-9772-079329e63159', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', 'a3cec998-adf9-410f-a0da-cc4ba790fbff', 7, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('35398367-b929-4449-b15e-5e72d3f68a2f', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', 'b5410655-21dd-4152-ac38-87eb7ecbadbf', 8, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('26c8ee05-7bd7-4794-af1e-a036a37083eb', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', 'aabb6e1a-400d-4a74-b2ca-3b6a05678133', 9, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('c19eff1d-7f72-4e0a-b99e-94a7e5f580fd', '3ce99078-b7df-4ab9-801a-138ba9a883eb', 'ec247d58-5813-4257-a241-f8ba141663e9', '1ff73c36-034d-4ae8-95d1-60a456f5b458', 10, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('1134289e-631c-48ce-bd91-5cbe5a46dbbf', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', '8882f966-8ee5-4d50-9630-0814be6876dd', 1, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('2035c208-6dec-43bd-9a0a-1670f6108ace', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', '81c9880d-0ac8-41b7-86ef-2b8479f001a3', 2, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('28516fe0-2798-4563-8b6b-21b34f44e966', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', 'd1659494-7f7c-4121-81f6-53ff5eed7edd', 3, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('97e20313-fa24-46d9-a2be-f104f8401875', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', 'e16ea688-f143-443c-ba3c-1863ba12c5d1', 4, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('07318f58-f471-4439-9cff-385a5027006c', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', 'c888434f-dd7c-4bce-abaa-3cafa2134eca', 5, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('0bfcc5a5-28eb-4507-ad0c-e6ef0e52362c', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', '51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 6, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('9a483e16-5b6f-4012-a2e5-d8321301b91b', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', '88ba4572-ce6c-4f3a-9296-042b112392d7', 7, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('6ade8d22-c680-4f91-957b-f90ff87b9309', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', 'ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 8, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('3c394b00-ef00-4fd5-8935-c7f40638a6ab', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', 'cf07a686-a2dd-4819-9827-9e129e58fac3', 9, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('cdbd8e4a-8eae-46a2-80ba-40cf91243917', 'fa8f78cc-ca63-409a-93f6-19225c7224fa', 'fae2f60a-5024-42bb-9886-ec082d5d8fc3', '9739d9f0-09c3-423f-b51e-274ac45e0d8c', 10, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('3e434bca-913e-4f04-8c7d-b03164e459b0', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '643378cf-27dd-4cde-a8f2-657d9449359d', 1, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('89499130-36de-4987-b2d6-96d177bc59e8', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '3b16303a-0f49-405d-b30f-bbd2752f5be1', 2, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('03a2cf91-1f17-412e-aa39-b49643edd464', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '3da97a34-1d05-456a-8859-083e82fb9395', 3, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('84fc5b8d-7451-456f-8304-b4e0f1f3dc86', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '61f9633f-9b12-4746-aa9e-11740ff4c191', 4, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('36081ebb-02d4-482c-8208-df9dd08f954b', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '09046eee-568e-4fbc-bcd4-6a49d7b32f87', 5, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('8bc395fb-3dc5-4908-a635-08c0dd58d092', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', 'ddb63565-cb08-48fe-8ec6-1687d03917f3', 6, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('898bf4b0-fc8c-42ec-a649-fb9309449108', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '42fb55e0-fdce-4bf8-9d7f-ad6db798652a', 7, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('9bb60c77-c817-4917-a0d6-eb77f2524b20', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '31699b07-0acd-4fc3-8713-46579dd9f447', 8, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('ecab6e39-956d-4043-9e32-de74fae96950', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '2a330872-43ab-4ac7-9226-b5a67341a6e9', 9, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('8d22803c-f910-477c-9d3b-670d7a42d650', 'd14dc73f-fd3a-44e9-b416-55827067ff1c', '3bf03cb8-5fb6-4cdd-9bbb-190196a7ab69', '421fe593-0d22-4265-94b3-e883098f2804', 10, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('21bacb08-f34e-46b1-bdaa-7ca96017d8cb', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', '8882f966-8ee5-4d50-9630-0814be6876dd', 1, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('62f32d19-f755-4b99-ae34-19b535d7a6a4', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', '81c9880d-0ac8-41b7-86ef-2b8479f001a3', 2, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('cbd0a888-b0db-4ab4-b5d6-2cbc8933127a', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', 'd1659494-7f7c-4121-81f6-53ff5eed7edd', 3, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('45357989-760e-45cf-a570-f658cda748ec', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', 'e16ea688-f143-443c-ba3c-1863ba12c5d1', 4, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('858867e0-d5c8-4f1a-aebc-866bb5254828', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', 'c888434f-dd7c-4bce-abaa-3cafa2134eca', 5, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('cc6ac3c4-627a-44f4-afc7-1e2e1570a090', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', '51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 6, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('eacb1c87-6018-4925-b789-7cef210883bc', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', '88ba4572-ce6c-4f3a-9296-042b112392d7', 7, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('92bb8d52-65b1-4049-8879-7aeca4fea0c7', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', 'ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 8, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('1b1cfc7d-501b-49cb-b41e-6bcdc47f4f64', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', 'cf07a686-a2dd-4819-9827-9e129e58fac3', 9, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('3f82a380-5822-4701-934a-0596101c2891', '9523172e-f342-4229-8ea2-3afa97eccd0b', 'd52bd12f-0c54-4083-acbf-708ef29d6a75', '9739d9f0-09c3-423f-b51e-274ac45e0d8c', 10, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('dcfd6a7f-80dd-4ffc-a4b2-996feeede9ed', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', 'f98dd36c-6152-49ca-95b8-dc8ff8254bbc', 1, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('c6abd61c-7aa3-4aa1-aefc-4064c642289b', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', 'ff3a145b-6bb4-40b3-857a-bebd70799c4c', 2, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('5cff11a8-b203-450b-8929-9d94247d2368', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', '63f41632-89e4-496b-be83-847b3af49755', 3, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('6eeede2e-045b-40e9-87b8-586a94bc5439', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', '3438d275-a415-4685-9a70-f1df19cab9eb', 4, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('ee830dbb-3743-4a09-bb53-f704b833f923', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', '60902f5b-3045-46cc-898f-c9e91493f323', 5, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('8c24cfc6-957c-4d56-8026-d75829c92548', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', 'c4c69d6e-a6d5-489f-acd4-5bace6445708', 6, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('c69cf3a2-6092-4e70-ac42-76e93a67b480', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', 'a3cec998-adf9-410f-a0da-cc4ba790fbff', 7, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('56dd695c-8c81-4266-b0c2-783eaa30d12c', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', 'b5410655-21dd-4152-ac38-87eb7ecbadbf', 8, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('ee85ebc8-a9e9-4b51-be7a-c37d10c7363d', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', 'aabb6e1a-400d-4a74-b2ca-3b6a05678133', 9, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('915f5ebb-d64a-44a2-b4e8-42906ae64bbb', '73f4246b-c573-4aba-939f-d532a353cddb', '6ddbbc23-b06f-4a70-b8cc-b3f9f042d7bc', '1ff73c36-034d-4ae8-95d1-60a456f5b458', 10, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('7cdc4f68-3b7e-4bbd-bf14-8926bd07531c', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '643378cf-27dd-4cde-a8f2-657d9449359d', 1, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('801242cb-4213-49a8-ad0b-6f05fdeb6546', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '3b16303a-0f49-405d-b30f-bbd2752f5be1', 2, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('27ff81bc-824f-4619-a27a-b4f3d4d2b765', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '3da97a34-1d05-456a-8859-083e82fb9395', 3, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('e2c2117a-956a-4e6e-b4be-e97f8bab94c3', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '61f9633f-9b12-4746-aa9e-11740ff4c191', 4, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('0b918d66-627b-44f8-b898-836917c1042c', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '09046eee-568e-4fbc-bcd4-6a49d7b32f87', 5, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('f779827a-0460-403f-80aa-6d00e8b93624', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', 'ddb63565-cb08-48fe-8ec6-1687d03917f3', 6, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('7c9fcaf4-08c8-4e86-af9a-9df8640b60fb', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '42fb55e0-fdce-4bf8-9d7f-ad6db798652a', 7, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('9747b220-acc2-4ca2-90aa-8655bedf5a85', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '31699b07-0acd-4fc3-8713-46579dd9f447', 8, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('76349809-c319-4a52-992b-476fd527cb3a', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '2a330872-43ab-4ac7-9226-b5a67341a6e9', 9, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('ca3381af-9f3b-4e04-83ca-dc2fdea9d4e2', '05d32cd8-92c4-4f81-a996-b19028a91734', '290ad277-ca62-4d2a-8653-b2e0974b8002', '421fe593-0d22-4265-94b3-e883098f2804', 10, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('b5115177-0b4d-4d07-ad8a-384eebf55f76', 'c2706a24-6811-4123-ab7b-60051b99c9d2', '8f3d0649-9d23-4c4c-a17c-e38ee01b60e2', '0f4a4f50-5f24-482d-9f27-26ef39464b08', 1, 5, 'null', NULL, 'short_answer', '');
INSERT INTO public.paper_questions VALUES ('9f36b195-d86e-4e8d-b08e-e25038ff4c4e', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', 'f98dd36c-6152-49ca-95b8-dc8ff8254bbc', 1, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('b34c84d8-782e-44ca-8299-b91168b9e21f', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', 'ff3a145b-6bb4-40b3-857a-bebd70799c4c', 2, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('fb883ad4-ae07-4e91-8b16-b4dc820b244c', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', '63f41632-89e4-496b-be83-847b3af49755', 3, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('1bc80ed5-7323-488a-8db9-97737acbcaf3', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', '3438d275-a415-4685-9a70-f1df19cab9eb', 4, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('a7f40ec8-2efe-4637-82c9-51e9dc7ccde6', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', '60902f5b-3045-46cc-898f-c9e91493f323', 5, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('5a257f0e-b80a-4507-9d08-8e1d5886602d', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', 'c4c69d6e-a6d5-489f-acd4-5bace6445708', 6, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('330b4808-ccc6-423e-b203-4896f2c4477d', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', 'a3cec998-adf9-410f-a0da-cc4ba790fbff', 7, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('57690865-7f20-459a-9d22-4c7c70089423', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', 'b5410655-21dd-4152-ac38-87eb7ecbadbf', 8, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('1752a8e1-b4ee-468c-9fd2-99a16d9e5454', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', 'aabb6e1a-400d-4a74-b2ca-3b6a05678133', 9, 5, 'null', NULL, 'short_answer', 'F');
INSERT INTO public.paper_questions VALUES ('125a3235-adc9-4335-bf4a-946eea43ac07', '84c6b2ec-2c09-430c-aea8-4660aaa6304a', 'edee95e8-9e2f-472e-b155-ddc8add706ae', '1ff73c36-034d-4ae8-95d1-60a456f5b458', 10, 5, 'null', NULL, 'short_answer', 'T');
INSERT INTO public.paper_questions VALUES ('2331cb8b-2723-4c6a-82a8-fa6b922e508e', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', '8882f966-8ee5-4d50-9630-0814be6876dd', 1, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('f652520c-df2b-4833-8b20-8674bad546d2', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', '81c9880d-0ac8-41b7-86ef-2b8479f001a3', 2, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('c41657ea-44c2-4579-b1e8-e4290252b94e', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', 'd1659494-7f7c-4121-81f6-53ff5eed7edd', 3, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('fb4833d0-ce35-4307-ac65-50391562a4f9', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', 'e16ea688-f143-443c-ba3c-1863ba12c5d1', 4, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('6b6abf33-89ac-4a38-a23f-2c83395711f9', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', 'c888434f-dd7c-4bce-abaa-3cafa2134eca', 5, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('948edfa6-8030-4e3c-bd44-ffafad2188ac', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', '51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 6, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('11c45aab-b2be-4727-af27-fed13b26bc05', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', '88ba4572-ce6c-4f3a-9296-042b112392d7', 7, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('147a2463-85e2-4dea-bd55-b5a42d57f86a', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', 'ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 8, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('28ffb5ac-d5a2-42c8-87b3-c93797112323', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', 'cf07a686-a2dd-4819-9827-9e129e58fac3', 9, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('a3d15ce6-2e07-4de4-a93c-c2f868826d0e', '24e05b5f-f682-45cc-85f6-48353f3c3f19', '432c934e-93d8-4fa4-bfd7-22c090c69078', '9739d9f0-09c3-423f-b51e-274ac45e0d8c', 10, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('40954954-739d-4739-a143-6fb6dcbe3ecb', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', '8882f966-8ee5-4d50-9630-0814be6876dd', 1, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('598973d3-b53f-4ec6-8e28-ec960423bc89', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', '81c9880d-0ac8-41b7-86ef-2b8479f001a3', 2, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('0e88469d-25a0-4a80-b54c-4f41ae3b0db1', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', 'd1659494-7f7c-4121-81f6-53ff5eed7edd', 3, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('2f42bcb3-a2ba-472e-8947-bd4ecec2be8e', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', 'e16ea688-f143-443c-ba3c-1863ba12c5d1', 4, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('b09f6811-ad6a-440b-b9a7-fb85b1313dc5', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', 'c888434f-dd7c-4bce-abaa-3cafa2134eca', 5, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('ed339217-ac96-4f58-bb94-ab89630f02ec', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', '51d31f39-34d9-49fc-b2cb-0d5be90b7c1f', 6, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('424499e7-a737-4f5d-bb8f-a6dad51bcc83', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', '88ba4572-ce6c-4f3a-9296-042b112392d7', 7, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('7924510d-76b8-415d-974e-5c0ba892ca9d', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', 'ca69a9a4-db6b-4b4d-b264-9edd24ce86cd', 8, 5, 'null', NULL, 'true_false', 'F');
INSERT INTO public.paper_questions VALUES ('62401a12-233c-4d5c-829d-d1c94384cba1', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', 'cf07a686-a2dd-4819-9827-9e129e58fac3', 9, 5, 'null', NULL, 'true_false', 'T');
INSERT INTO public.paper_questions VALUES ('4fb3d61e-ca4f-499f-977e-5dcb37481ba8', 'f39b7deb-227c-4835-a893-f7ea5958e164', '7bd6cc0d-a2a8-4829-a0f4-8ed7cf4a3c8f', '9739d9f0-09c3-423f-b51e-274ac45e0d8c', 10, 5, 'null', NULL, 'true_false', 'F');


--
-- Data for Name: system_configs; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.system_configs VALUES ('model_providers', '{"providers": [{"id": "32e07caa-08b8-4952-966a-1e33d572024a", "name": "vLLM", "model": "/home/dell/models/Qwen3.5-27B", "api_key": "", "enabled": true, "base_url": "http://192.168.31.18:8001/v1", "provider_type": "vllm"}, {"id": "41ad44da-8d3c-4fd3-ba37-8b45292031c4", "name": "Google AI", "model": "gemini-2.5-pro", "api_key": "AIzaSyDFCw8eInHp9H-Wa6bgbXtq9E0rFVayDco", "enabled": true, "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "provider_type": "google"}]}', '2026-04-13 13:50:11.203762+00', 'admin');
INSERT INTO public.system_configs VALUES ('module_assignments', '{"review": "41ad44da-8d3c-4fd3-ba37-8b45292031c4", "scoring": "41ad44da-8d3c-4fd3-ba37-8b45292031c4", "indicator": "41ad44da-8d3c-4fd3-ba37-8b45292031c4", "annotation": "41ad44da-8d3c-4fd3-ba37-8b45292031c4", "interactive": "41ad44da-8d3c-4fd3-ba37-8b45292031c4", "paper_import": "41ad44da-8d3c-4fd3-ba37-8b45292031c4", "paper_generation": "41ad44da-8d3c-4fd3-ba37-8b45292031c4", "question_generation": "41ad44da-8d3c-4fd3-ba37-8b45292031c4"}', '2026-04-13 14:46:37.421434+00', 'keven');


--
-- PostgreSQL database dump complete
--

\unrestrict Ti2eXBmPxKI7BcqHJfPO7A0tT9G0qPaYXExznP5BuiSrCMI3wTbdpTIhCt1X95h

