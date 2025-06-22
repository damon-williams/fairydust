--
-- PostgreSQL database dump
--

-- Dumped from database version 16.8 (Debian 16.8-1.pgdg120+1)
-- Dumped by pg_dump version 16.9 (Homebrew)

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

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: app_model_configs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.app_model_configs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    app_id uuid NOT NULL,
    primary_provider character varying(50) NOT NULL,
    primary_model_id character varying(100) NOT NULL,
    primary_parameters jsonb DEFAULT '{}'::jsonb,
    fallback_models jsonb DEFAULT '[]'::jsonb,
    cost_limits jsonb DEFAULT '{}'::jsonb,
    feature_flags jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.app_model_configs OWNER TO postgres;

--
-- Name: apps; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.apps (
    id uuid NOT NULL,
    builder_id uuid,
    name character varying(255) NOT NULL,
    slug character varying(255) NOT NULL,
    description text,
    icon_url text,
    dust_per_use integer DEFAULT 5 NOT NULL,
    is_active boolean DEFAULT true,
    is_approved boolean DEFAULT false,
    category character varying(100),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    website_url text,
    demo_url text,
    callback_url text,
    admin_notes text,
    registration_source character varying(50) DEFAULT 'web'::character varying,
    registered_by_service character varying(255),
    registration_metadata jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE public.apps OWNER TO postgres;

--
-- Name: COLUMN apps.registration_source; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.apps.registration_source IS 'Source of registration: web, mcp, api, admin';


--
-- Name: COLUMN apps.registered_by_service; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.apps.registered_by_service IS 'Service account ID if registered via service token';


--
-- Name: COLUMN apps.registration_metadata; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.apps.registration_metadata IS 'Additional metadata about registration (MCP version, etc.)';


--
-- Name: dust_transactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.dust_transactions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    amount integer NOT NULL,
    type character varying(50) NOT NULL,
    description text,
    app_id uuid,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    idempotency_key character varying(255),
    status character varying(50) DEFAULT 'completed'::character varying,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.dust_transactions OWNER TO postgres;

--
-- Name: hourly_app_stats; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.hourly_app_stats (
    app_id uuid NOT NULL,
    hour timestamp with time zone NOT NULL,
    unique_users integer DEFAULT 0 NOT NULL,
    transactions integer DEFAULT 0 NOT NULL,
    dust_consumed integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.hourly_app_stats OWNER TO postgres;

--
-- Name: llm_cost_tracking; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.llm_cost_tracking (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    app_id uuid,
    tracking_date date NOT NULL,
    tracking_month character varying(7) NOT NULL,
    total_requests integer DEFAULT 0,
    total_tokens integer DEFAULT 0,
    total_cost_usd numeric(10,6) DEFAULT 0,
    model_usage jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.llm_cost_tracking OWNER TO postgres;

--
-- Name: llm_usage_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.llm_usage_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    app_id uuid NOT NULL,
    provider character varying(50) NOT NULL,
    model_id character varying(100) NOT NULL,
    prompt_tokens integer NOT NULL,
    completion_tokens integer NOT NULL,
    total_tokens integer NOT NULL,
    cost_usd numeric(10,6) NOT NULL,
    latency_ms integer NOT NULL,
    prompt_hash character varying(64),
    finish_reason character varying(50),
    was_fallback boolean DEFAULT false,
    fallback_reason character varying(100),
    request_metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.llm_usage_logs OWNER TO postgres;

--
-- Name: people_in_my_life; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.people_in_my_life (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name character varying(100) NOT NULL,
    age_range character varying(50),
    relationship character varying(100),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.people_in_my_life OWNER TO postgres;

--
-- Name: person_profile_data; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.person_profile_data (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    person_id uuid NOT NULL,
    user_id uuid NOT NULL,
    category character varying(50) NOT NULL,
    field_name character varying(100) NOT NULL,
    field_value jsonb NOT NULL,
    confidence_score double precision DEFAULT 1.0,
    source character varying(50) DEFAULT 'user_input'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.person_profile_data OWNER TO postgres;

--
-- Name: profiling_questions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.profiling_questions (
    id character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    question_text text NOT NULL,
    question_type character varying(50) NOT NULL,
    profile_field character varying(100) NOT NULL,
    priority integer DEFAULT 5 NOT NULL,
    app_context jsonb,
    min_app_uses integer DEFAULT 0,
    options jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    is_active boolean DEFAULT true
);


ALTER TABLE public.profiling_questions OWNER TO postgres;

--
-- Name: user_auth_providers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_auth_providers (
    user_id uuid NOT NULL,
    provider character varying(50) NOT NULL,
    provider_user_id character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.user_auth_providers OWNER TO postgres;

--
-- Name: user_profile_data; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_profile_data (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    category character varying(50) NOT NULL,
    field_name character varying(100) NOT NULL,
    field_value jsonb NOT NULL,
    confidence_score double precision DEFAULT 1.0,
    source character varying(50) DEFAULT 'user_input'::character varying,
    app_context character varying(50),
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_confidence_score CHECK (((confidence_score >= (0.0)::double precision) AND (confidence_score <= (1.0)::double precision)))
);


ALTER TABLE public.user_profile_data OWNER TO postgres;

--
-- Name: user_question_responses; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_question_responses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    question_id character varying(100) NOT NULL,
    response_value jsonb NOT NULL,
    session_id character varying(100),
    dust_reward integer DEFAULT 0,
    answered_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.user_question_responses OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    fairyname character varying(50) NOT NULL,
    email character varying(255),
    phone character varying(20),
    avatar_url text,
    is_builder boolean DEFAULT false,
    is_active boolean DEFAULT true,
    dust_balance integer DEFAULT 0,
    auth_provider character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    is_admin boolean DEFAULT false,
    last_name character varying(100),
    first_name character varying(100),
    age_range character varying(20),
    city character varying(100),
    country character varying(100) DEFAULT 'US'::character varying,
    last_profiling_session timestamp without time zone,
    total_profiling_sessions integer DEFAULT 0,
    CONSTRAINT check_contact CHECK (((email IS NOT NULL) OR (phone IS NOT NULL)))
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Data for Name: app_model_configs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.app_model_configs (id, app_id, primary_provider, primary_model_id, primary_parameters, fallback_models, cost_limits, feature_flags, created_at, updated_at) FROM stdin;
43da5c59-d634-444b-a0f5-eb6085068e96	46f666d2-defe-4172-b847-2377caa3449f	anthropic	claude-3-5-haiku-20241022	{"top_p": 0.9, "max_tokens": 150, "temperature": 0.8}	[{"trigger": "provider_error", "model_id": "gpt-4o-mini", "provider": "openai", "parameters": {"max_tokens": 150, "temperature": 0.8}}]	{"daily_max": 10.0, "monthly_max": 100.0, "per_request_max": 0.05}	{"log_prompts": false, "cache_responses": true, "streaming_enabled": true}	2025-06-21 14:47:56.900031+00	2025-06-21 15:18:28.205431+00
\.


--
-- Data for Name: apps; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.apps (id, builder_id, name, slug, description, icon_url, dust_per_use, is_active, is_approved, category, created_at, updated_at, status, website_url, demo_url, callback_url, admin_notes, registration_source, registered_by_service, registration_metadata) FROM stdin;
4c890b06-e8a0-494e-9445-5fad2e1124af	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	Yoga Playlist Generator	yoga-playlist-generator	AI-powered yoga playlist generator that creates custom Spotify playlists matching your yoga flow with perfectly synchronized music.	https://yoga-playlist.app/icon.png	5	t	f	creative	2025-06-04 21:58:37.582775+00	2025-06-04 21:59:45.805214+00	approved	https://yoga-playlist.app	https://yoga-playlist.app/demo	https://yoga-playlist.app/api/fairydust-webhook	\N	web	\N	{}
678b9097-6d3b-4f58-9d0f-81f9af551697	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	Dad Jokes	dad-jokes	Dad joke generator	string	5	t	t	entertainment	2025-06-17 03:38:45.781+00	2025-06-17 03:38:45.781+00	approved	string	string	string	\N	web	\N	{}
46f666d2-defe-4172-b847-2377caa3449f	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	Inspire	fairydust-inspire	Inspire	string	5	t	f	productivity	2025-06-20 15:01:10.504+00	2025-06-20 15:06:46.543+00	approved	string	string	string	Approved by stellardawn2947	web	\N	{}
c09cb322-bfc7-4330-9bb5-0eaaac98a636	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	Recipes	fairydust-recipes	fairydust Recipes	string	5	t	f	productivity	2025-06-20 16:44:12.64014+00	2025-06-20 17:24:12.591188+00	approved	string	string	string	Approved by stellardawn2947	web	\N	{}
9d298750-98d3-40c1-b552-287ffe32534d	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	Original Recipe Generator	original-recipe-generator	Recipe generation	\N	5	t	f	productivity	2025-06-17 15:06:01.267+00	2025-06-17 15:06:01.267+00	approved	https://recipe-agent-team-production.up.railway.app/	\N	\N	\N	web	\N	{}
\.


--
-- Data for Name: dust_transactions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.dust_transactions (id, user_id, amount, type, description, app_id, metadata, created_at, idempotency_key, status, updated_at) FROM stdin;
0ddfbc08-e3e0-47b5-92c3-852700e818ce	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	25	grant	Welcome bonus	\N	\N	2025-06-04 21:55:47.73581+00	\N	completed	2025-06-04 21:55:47.73581+00
497398f5-23f6-4bb6-bb83-b7363e2501fe	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-04 23:32:11.205218+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749079931013-ck0lxwks6	completed	2025-06-04 23:32:11.205218+00
c8512a74-339f-46db-aeca-b9cecae3e41a	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-04 23:32:44.36986+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749079964251-e4jj64b7y	completed	2025-06-04 23:32:44.36986+00
ec3818e3-9f54-4e2e-9b47-2d9566bce658	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-04 23:48:00.007781+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749080879768-1gt9hpd4s	completed	2025-06-04 23:48:00.007781+00
f01369aa-a12d-4835-b5fe-12d507c62bcc	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-04 23:53:11.564758+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749081191320-qzzkwd6nd	completed	2025-06-04 23:53:11.564758+00
f3c72412-adb4-4b89-b46b-38a48fa3acfe	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 00:01:40.505838+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749081700344-b4yhxcv36	completed	2025-06-05 00:01:40.505838+00
fac88413-a94f-423f-88f6-8c01e8e46153	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 00:07:21.830194+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749082041657-z2iccszrj	completed	2025-06-05 00:07:21.830194+00
cd4d19d6-b464-4809-a60c-1864182efd23	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 00:08:03.921529+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749082083803-tlfopd0fg	completed	2025-06-05 00:08:03.921529+00
d3874297-4075-4ded-a70a-06ec0563c988	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 00:08:56.24944+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749082136160-tl797kbvi	completed	2025-06-05 00:08:56.24944+00
9633e59d-4197-4a6d-af8d-05cf48d76834	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 00:09:09.823675+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749082149707-wwrfekm4y	completed	2025-06-05 00:09:09.823675+00
5769e430-5529-4170-b65e-286d5891ac3a	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 00:09:19.547984+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749082159464-suhmhc5dc	completed	2025-06-05 00:09:19.547984+00
c0938587-c415-46e9-856f-542f92d6a4a6	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 00:09:24.42798+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749082164332-qjbrr0456	completed	2025-06-05 00:09:24.42798+00
be126879-bc2e-4f48-bd88-1f975e509b3b	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 00:16:54.05677+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749082613887-2kn01591p	completed	2025-06-05 00:16:54.05677+00
cbd2a437-2c93-470e-9179-f47d1ea60c60	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	100	grant	Admin production setup	\N	\N	2025-06-05 02:05:42.658076+00	\N	completed	2025-06-05 02:05:42.658076+00
27687c71-1835-4002-968c-7cca3fb21b63	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	100	grant	Admin production setup	\N	\N	2025-06-05 02:05:59.313046+00	\N	completed	2025-06-05 02:05:59.313046+00
111287cd-aed0-4eaa-ab6e-2726b580f5ec	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 17:34:57.558227+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749144897274-x91uxw4ul	completed	2025-06-05 17:34:57.558227+00
64864fc4-6f8e-4b39-bda1-b540c92ac34b	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:27:37.771052+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749148057550-i2cwa2qrz	completed	2025-06-05 18:27:37.771052+00
8db913de-a3aa-4c63-b652-99d3cbb71345	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:33:15.016616+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749148394747-3dtsx9ial	completed	2025-06-05 18:33:15.016616+00
cfe0a36e-2036-4e35-afdd-9dd38b10a62c	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:33:55.814005+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749148435684-8yztdsgb5	completed	2025-06-05 18:33:55.814005+00
c4d4dcda-213f-448a-a622-3bfca2eca5fd	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:40:10.529143+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749148810328-w4rpey5gy	completed	2025-06-05 18:40:10.529143+00
95b4064b-02bb-4b60-865c-3442025ee006	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:41:36.758051+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749148896627-ws9gij2mq	completed	2025-06-05 18:41:36.758051+00
9205c7db-4955-45fd-b1b4-1c9de38da3fd	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:41:41.80093+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749148901705-c8k5nds8h	completed	2025-06-05 18:41:41.80093+00
e708a089-4432-4f63-91d4-951bcd4659a1	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:42:15.020533+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749148934923-e4n88uh9p	completed	2025-06-05 18:42:15.020533+00
54a3e657-409b-4651-b0fd-a57b4830cb08	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:52:21.928257+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749149541699-qj9ta1bkz	completed	2025-06-05 18:52:21.928257+00
57bc485c-7cc0-4eb3-bf83-09bc321d8b51	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:53:17.180842+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749149597075-yleih3q1x	completed	2025-06-05 18:53:17.180842+00
d91e11b8-ded9-4424-8111-fb2f77f8628d	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:54:04.478951+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749149644359-d6kvffqjl	completed	2025-06-05 18:54:04.478951+00
50c0c09e-ca46-4572-92f1-9be9aeb91425	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:57:37.894811+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749149857773-vnmd5c5ua	completed	2025-06-05 18:57:37.894811+00
f5a34e9b-16e8-411b-affc-7dfcf43a393a	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 18:58:30.225486+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749149910131-0x5mu7qyd	completed	2025-06-05 18:58:30.225486+00
9ee7ab3d-67d7-4a91-afe4-bf9eefd39d56	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 19:03:25.690889+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749150205546-ca1ruvf43	completed	2025-06-05 19:03:25.690889+00
a8e69abe-b6b9-4e6a-bdfe-32585a5f53fd	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 19:11:11.622176+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749150671401-9fsneyba3	completed	2025-06-05 19:11:11.622176+00
d419a051-4351-4302-b879-9581c5918668	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 19:16:12.552879+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749150972311-4q9ysvevm	completed	2025-06-05 19:16:12.552879+00
8632e5c1-f9ac-49a9-ba94-b759567a6dfd	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 19:22:43.746718+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749151363498-bz9y7osls	completed	2025-06-05 19:22:43.746718+00
04aed816-2b96-42b4-b9f7-2fb5a814c7f0	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 19:26:54.772873+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749151614639-kl69hchc7	completed	2025-06-05 19:26:54.772873+00
2db1e81e-a948-4cc6-bcb0-753c3d808650	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-05 19:27:56.869507+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1749151676687-bqw9khoqo	completed	2025-06-05 19:27:56.869507+00
9f73c667-ac0c-46dc-a2df-fb5c8aa24ab7	3f40b36f-c600-4075-8974-3f6c5f21f557	25	grant	Welcome bonus	\N	\N	2025-06-11 15:50:04.007447+00	\N	completed	2025-06-11 15:50:04.007447+00
115b707d-ada0-4b05-9701-a575a6ad5a58	3f40b36f-c600-4075-8974-3f6c5f21f557	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-11 15:50:11.653295+00	3f40b36f-c600-4075-8974-3f6c5f21f557-1749657011092-k7mtk3db2	completed	2025-06-11 15:50:11.653295+00
7cf379cb-4918-467f-8b07-8637639aac12	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-15 23:35:43.623451+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750030543038-ovxvqk7rg	completed	2025-06-15 23:35:43.623451+00
d3e7ad15-599e-4b44-a77b-4c0e58a07664	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-15 23:46:22.463345+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750031181869-jcvck756a	completed	2025-06-15 23:46:22.463345+00
7cb22c38-c155-434f-834e-ac46463f9c0b	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 00:04:39.907081+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750032279416-h3xyqcnzr	completed	2025-06-16 00:04:39.907081+00
ba0ce241-2cdc-42e9-b874-885961e9cdbf	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 00:13:59.483205+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750032839004-bq50hwydp	completed	2025-06-16 00:13:59.483205+00
74b6ba0e-d87b-4a8b-acbf-a59e21765c73	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 01:14:18.533058+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750036457953-43shmf7ci	completed	2025-06-16 01:14:18.533058+00
d731f6ef-163b-4b54-8224-3eaaf855aa60	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 01:19:46.776767+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750036786221-n7mxth3iz	completed	2025-06-16 01:19:46.776767+00
62ead4fe-a4bb-4775-9c39-3ede78bc7862	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 01:26:46.087689+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750037205546-hby36js06	completed	2025-06-16 01:26:46.087689+00
73eec834-49e3-4ab2-8a9f-13e52e275059	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 01:29:21.337695+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750037360948-uza6knwkx	completed	2025-06-16 01:29:21.337695+00
c93599e5-1c57-4fe5-a465-5ea7cf2e055d	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 01:53:45.715881+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750038825247-mg14p44au	completed	2025-06-16 01:53:45.715881+00
e729a7a6-9c4d-418c-bf0a-722a23673b26	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:03:31.405036+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750039410930-q5ruq2qtw	completed	2025-06-16 02:03:31.405036+00
45037c50-d176-4504-b531-32b28d1a5f88	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:07:26.312641+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750039645930-g65tgwjmb	completed	2025-06-16 02:07:26.312641+00
f1d4673b-0d39-4c2a-a340-10a90aefa5dc	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:16:55.332737+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750040214858-yxhzuzkir	completed	2025-06-16 02:16:55.332737+00
6b70af03-8f26-44ac-90e5-ba7fe549c6b1	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:23:48.3691+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750040627908-odvberfa3	completed	2025-06-16 02:23:48.3691+00
eac47474-7a7f-4abb-b04c-51ff1272597e	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:25:14.2113+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750040713810-6nb3azgwg	completed	2025-06-16 02:25:14.2113+00
71bc408c-716e-4d23-b162-92e4c63f3aab	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:26:31.01682+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750040790576-v2re8dsek	completed	2025-06-16 02:26:31.01682+00
9fae613b-1d01-4cbf-b1d1-34e221bd087e	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:27:27.705145+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750040847445-ak46s1wkr	completed	2025-06-16 02:27:27.705145+00
68b1ad38-1b80-4d9c-9c87-3f19df415397	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:27:39.851408+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750040859608-cg3lhxs84	completed	2025-06-16 02:27:39.851408+00
920e2097-259c-4bcb-8b87-91da93664d60	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:28:43.343381+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750040922746-ofobeh2fn	completed	2025-06-16 02:28:43.343381+00
4e6dae7d-62e7-45ba-a1ae-794c69db947d	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:31:25.654691+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750041085185-bii5vry2w	completed	2025-06-16 02:31:25.654691+00
8a7faa2e-8ecb-4509-ba40-2e3f4f4ede88	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:33:22.655141+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750041202427-aj9hd3ij1	completed	2025-06-16 02:33:22.655141+00
2bfbecaf-fae6-443b-b708-723a89a151cb	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 02:33:53.917357+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750041233546-52zfccrdl	completed	2025-06-16 02:33:53.917357+00
642ebedf-bc55-4d4d-8675-3faa868348c2	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 03:00:49.954688+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750042849470-yz9rfyqlf	completed	2025-06-16 03:00:49.954688+00
a448c3e0-a644-41a6-9146-6d94229ad78b	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 03:08:41.9255+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750043321541-z2lo8ce80	completed	2025-06-16 03:08:41.9255+00
bdc0d639-3f56-4c65-be30-b02f4cc3f47d	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 03:09:36.237975+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750043375988-g39f00fup	completed	2025-06-16 03:09:36.237975+00
21678a56-0c9b-4efb-8688-1a4c08b755cb	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 03:12:52.94614+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750043572537-73lyn2p28	completed	2025-06-16 03:12:52.94614+00
93bd31ea-4e86-40a0-abd3-e0a138164460	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 14:44:18.601012+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750085055579-tvya569sa	completed	2025-06-16 14:44:18.601012+00
b3c76ab6-abdb-408e-9be1-09011b237155	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 14:45:31.908773+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750085130832-fm8fcp385	completed	2025-06-16 14:45:31.908773+00
d8caae31-689a-4d2c-acfe-c97e09cfb751	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 14:56:44.535288+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750085802549-bae2ctbjz	completed	2025-06-16 14:56:44.535288+00
850d09f9-937a-4f18-a1bf-8cbb56f6521b	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 15:11:30.418546+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750086688931-z4de232yr	completed	2025-06-16 15:11:30.418546+00
545479d9-8b18-4fd3-a2cc-c4ebe96a1d12	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 15:25:37.264994+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750087534977-p8entnjtm	completed	2025-06-16 15:25:37.264994+00
2bbacce2-5be7-4908-bea7-ee5161734abd	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 15:49:18.544276+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750088955834-ofhvfi9wp	completed	2025-06-16 15:49:18.544276+00
66a9085a-b46e-462d-b744-a1ec2d074f92	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 16:07:39.840225+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750090057346-xqx1h160u	completed	2025-06-16 16:07:39.840225+00
093cceeb-0857-47da-8395-15cb1b9f8188	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 16:21:41.327354+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750090898794-i44g5vicr	completed	2025-06-16 16:21:41.327354+00
c6f15ec5-57e4-47a8-8d50-a31a1f8a6973	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 16:28:45.254676+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750091323465-imxkfq7va	completed	2025-06-16 16:28:45.254676+00
0cf7d92e-ebeb-4b22-b289-a6038dc4121a	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 21:55:09.516599+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750110909225-bw44b84yj	completed	2025-06-16 21:55:09.516599+00
cb877e15-0b70-4ecb-9890-97071e4b693d	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 21:55:43.976582+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750110943830-savtjwayg	completed	2025-06-16 21:55:43.976582+00
a01af904-07db-4f84-9c2d-6d7eede16c0a	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 21:56:34.352499+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750110994212-4extu4zvo	completed	2025-06-16 21:56:34.352499+00
2c64c9df-1904-46b3-a781-512e77dcc841	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 22:02:44.647934+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750111364391-qf5pmoum7	completed	2025-06-16 22:02:44.647934+00
d0b68d2f-f06e-450d-8046-975b9b6137ec	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 22:03:30.602226+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750111410487-ezhcp23ha	completed	2025-06-16 22:03:30.602226+00
5cdfe74a-9459-4ef9-a68b-388eb24df091	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 22:43:41.111749+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750113820927-o5m2a73yk	completed	2025-06-16 22:43:41.111749+00
c89c33da-a270-4db8-8d46-c70e1f34ec8c	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-16 22:49:47.534977+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750114187390-73zyq1uh6	completed	2025-06-16 22:49:47.534977+00
fe29a772-ddbc-4654-bc89-b06d9f273c6a	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-17 15:01:16.577925+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750172476190-4t6007uh5	completed	2025-06-17 15:01:16.577925+00
4c9bf3d5-4254-41bc-9e2b-d6c3744c3910	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-17 16:08:37.881285+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750176517575-n3hx3iqqz	completed	2025-06-17 16:08:37.881285+00
71704c0f-4afb-4bb8-9b16-0b80e15d4513	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-17 16:10:03.437542+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750176603133-ek8neq23h	completed	2025-06-17 16:10:03.437542+00
0d398591-7209-4fd7-a8cb-b4616261eac5	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-5	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-17 17:11:12.827236+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750180272510-mjztzfsfh	completed	2025-06-17 17:11:12.827236+00
93256810-a003-4269-84fd-d894305680b6	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-5	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-17 17:11:28.902866+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750180288712-bygflegng	completed	2025-06-17 17:11:28.902866+00
300c51ec-e577-4e9e-9c46-9d7d8234586e	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-17 17:17:14.361511+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750180634073-n6asznjh5	completed	2025-06-17 17:17:14.361511+00
2a79599b-461b-4aa4-a9a2-16b017704309	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-5	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-17 17:18:08.24205+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750180688018-ndjesggdl	completed	2025-06-17 17:18:08.24205+00
262f204f-d3bb-4d60-832a-c8398227f374	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-5	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-17 17:23:51.415407+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750181031140-ci1f7zasr	completed	2025-06-17 17:23:51.415407+00
118ae395-6055-48ae-9ee2-b55f835259d7	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-5	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-17 17:24:16.13301+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750181055919-y3q0513v1	completed	2025-06-17 17:24:16.13301+00
13fac062-8993-4e40-b403-253e26107be6	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-5	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-17 17:27:00.797902+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750181220665-ewifpjt8r	completed	2025-06-17 17:27:00.797902+00
e0766450-69cb-4089-9fc0-261beb86ea60	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-5	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-17 17:27:16.954517+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750181236831-klaz3c29i	completed	2025-06-17 17:27:16.954517+00
f6196fe9-416f-4e2c-9345-69798d5607e5	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-5	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-17 17:27:22.390014+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750181242264-c3ukeo4kz	completed	2025-06-17 17:27:22.390014+00
4e051205-a29c-45d8-9aa6-316e918cd191	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-18 15:57:55.640449+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750262275269-dttqyh4zg	completed	2025-06-18 15:57:55.640449+00
bc331b77-db1c-45a6-bea2-191718540ba5	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-18 17:15:48.821311+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750266948452-rbrkhj2ok	completed	2025-06-18 17:15:48.821311+00
434c6f88-f9c3-4435-975d-d26f2f613c32	6d9d7423-3c9b-4c97-b97e-7fdb275aa789	25	grant	Welcome bonus	\N	\N	2025-06-18 17:40:37.28167+00	\N	completed	2025-06-18 17:40:37.28167+00
0ab68450-c630-4e78-b21d-ca1eb224c12f	6d9d7423-3c9b-4c97-b97e-7fdb275aa789	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-18 17:41:01.719669+00	6d9d7423-3c9b-4c97-b97e-7fdb275aa789-1750268461528-cmi7n088d	completed	2025-06-18 17:41:01.719669+00
788b6418-c4b7-44f5-8abe-c2b460d5bc9d	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-18 17:50:03.278157+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750269003081-ukak9fxv5	completed	2025-06-18 17:50:03.278157+00
3414d94c-f88b-4e69-9f88-86c82ad30738	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-18 17:50:26.158095+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750269026064-6kffw5ea9	completed	2025-06-18 17:50:26.158095+00
47d4e7d5-691e-490e-813f-3479cb148a29	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-18 21:33:16.915234+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750282396694-lqqsedqyp	completed	2025-06-18 21:33:16.915234+00
2a1b9ddb-699a-48d1-a4fc-7f4623890889	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-18 21:34:15.348511+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750282455214-bih3hxf7u	completed	2025-06-18 21:34:15.348511+00
7d55c99d-75e2-46fd-94bc-58c824b2ac4b	6ff1f86a-5b22-49d3-8785-247780e2e2cf	25	grant	Welcome bonus	\N	\N	2025-06-18 21:54:01.455836+00	\N	completed	2025-06-18 21:54:01.455836+00
46df855c-bef0-4899-aaed-1ead2979a3c7	6ff1f86a-5b22-49d3-8785-247780e2e2cf	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-18 21:54:05.903637+00	6ff1f86a-5b22-49d3-8785-247780e2e2cf-1750283645445-ioldguwz2	completed	2025-06-18 21:54:05.903637+00
57224c4e-e1a2-4fef-8e68-b6f217351f94	d40d539a-9124-4a78-9589-b00f0b89b17f	25	grant	Welcome bonus	\N	\N	2025-06-18 23:17:18.362256+00	\N	completed	2025-06-18 23:17:18.362256+00
be18519e-05cd-4323-861f-5d902570a199	d40d539a-9124-4a78-9589-b00f0b89b17f	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-18 23:17:25.33114+00	d40d539a-9124-4a78-9589-b00f0b89b17f-1750288644972-ygz51ilut	completed	2025-06-18 23:17:25.33114+00
5e7d2028-2011-46e3-8a87-c80905b41d34	d40d539a-9124-4a78-9589-b00f0b89b17f	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-18 23:27:40.187328+00	d40d539a-9124-4a78-9589-b00f0b89b17f-1750289259884-h2iag589h	completed	2025-06-18 23:27:40.187328+00
d3ea5acc-abaa-45e5-8ba1-fc753a2b693c	d40d539a-9124-4a78-9589-b00f0b89b17f	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-19 01:42:43.54243+00	d40d539a-9124-4a78-9589-b00f0b89b17f-1750297363279-5kpd0lvo5	completed	2025-06-19 01:42:43.54243+00
4ec6b40b-7d10-4e43-8513-990e12ba61ea	d40d539a-9124-4a78-9589-b00f0b89b17f	-2	consume	Consumed for Generate Playlist - Yoga Playlist Generator	4c890b06-e8a0-494e-9445-5fad2e1124af	\N	2025-06-19 01:43:07.023312+00	d40d539a-9124-4a78-9589-b00f0b89b17f-1750297386840-0faxoasjm	completed	2025-06-19 01:43:07.023312+00
be291041-3054-4ddd-86b9-47aec8e350b4	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-19 03:29:57.072956+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750303796844-fnmzr8snm	completed	2025-06-19 03:29:57.072956+00
9de8e028-6200-45ad-b89d-46c08061a022	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for Generate Joke - Dad Joke Generator	678b9097-6d3b-4f58-9d0f-81f9af551697	\N	2025-06-19 03:30:56.812096+00	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b-1750303856637-t9yz1njyb	completed	2025-06-19 03:30:56.812096+00
0bda74cd-97f3-41ee-b0cc-ef002e936ecc	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	10	grant	signup_bonus	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 04:01:25.154109+00	\N	completed	2025-06-20 04:01:25.154109+00
12a52d7b-2157-4843-8140-3c05294167f2	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	10	grant	signup_bonus	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 04:14:34.373895+00	\N	completed	2025-06-20 04:14:34.373895+00
1717a49c-bed0-4b21-a38f-b326d611b9db	d40d539a-9124-4a78-9589-b00f0b89b17f	55	admin_grant	Admin grant: Admin grant	\N	\N	2025-06-20 04:20:01.107995+00	\N	completed	2025-06-20 04:20:01.107995+00
e51d7741-a758-4aeb-a930-a23437eca231	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	10	grant	signup_bonus	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 04:56:51.332064+00	\N	completed	2025-06-20 04:56:51.332064+00
7cb8d6f5-042d-46e9-9789-d88fb0e036ad	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	10	grant	profile_completion	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 04:59:07.89672+00	\N	completed	2025-06-20 04:59:07.89672+00
28f40e31-1637-4173-8f0e-a9e4f826d242	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	10	grant	signup_bonus	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 14:57:16.642401+00	\N	completed	2025-06-20 14:57:16.642401+00
6ab5e9c3-ed78-420d-a574-3adf77cc1431	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_something_good_for_me	46f666d2-defe-4172-b847-2377caa3449f	{"category": "Something good for me"}	2025-06-20 15:07:40.575908+00	something_good_for_me_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750432060365_bajxl7l2q	completed	2025-06-20 15:07:40.575908+00
2aebe7e1-80f5-4f40-936e-b18ad87c0c0a	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_a_creative_spark	46f666d2-defe-4172-b847-2377caa3449f	{"category": "A creative spark"}	2025-06-20 15:08:58.617461+00	a_creative_spark_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750432138458_i6abn7cdp	completed	2025-06-20 15:08:58.617461+00
26349a9f-7f16-40bc-a973-f77833ea00b5	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_something_good_for_me	46f666d2-defe-4172-b847-2377caa3449f	{"category": "Something good for me"}	2025-06-20 15:11:05.010375+00	something_good_for_me_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750432264766_rm9ffulrj	completed	2025-06-20 15:11:05.010375+00
7d045f5e-bd0a-48ec-b325-3c8a15e34273	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_something_good_for_me	46f666d2-defe-4172-b847-2377caa3449f	{"category": "Something good for me"}	2025-06-20 15:11:39.190998+00	something_good_for_me_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750432298967_h0od64vbx	completed	2025-06-20 15:11:39.190998+00
fb7e53bd-63bc-4b92-8626-b4368f6c9be1	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_something_good_for_me	46f666d2-defe-4172-b847-2377caa3449f	{"category": "Something good for me"}	2025-06-20 15:11:48.775882+00	something_good_for_me_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750432308585_7lxt14xj2	completed	2025-06-20 15:11:48.775882+00
5fc385d7-b8e3-46a0-b22c-66d140a7dbba	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_something_good_for_me	46f666d2-defe-4172-b847-2377caa3449f	{"category": "Something good for me"}	2025-06-20 15:11:54.339517+00	something_good_for_me_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750432314185_z7duadpvj	completed	2025-06-20 15:11:54.339517+00
e9405404-8178-4f8d-bdf2-29343d59e109	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	10	grant	signup_bonus	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 17:23:29.241628+00	\N	completed	2025-06-20 17:23:29.241628+00
aff08148-5c91-4fb0-bb1e-98ba9356199f	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-3	consume	Consumed for inspire_generation	c09cb322-bfc7-4330-9bb5-0eaaac98a636	{"dish": "hummus", "exclude": "", "include": "", "complexity": "Simple"}	2025-06-20 17:26:02.561726+00	app_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750440362375_6exijcsh7	completed	2025-06-20 17:26:02.561726+00
ccc4b1c2-cc55-4b12-a08c-5d5ca864b2a5	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-3	consume	Consumed for inspire_generation	c09cb322-bfc7-4330-9bb5-0eaaac98a636	{"dish": "hummus", "exclude": "", "include": "", "complexity": "Simple"}	2025-06-20 17:48:19.159148+00	app_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750441698459_qv06hbt0f	completed	2025-06-20 17:48:19.159148+00
fd38125c-df30-4433-8aa2-795a4a239f94	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-3	consume	Consumed for inspire_generation	c09cb322-bfc7-4330-9bb5-0eaaac98a636	{"dish": "pho", "exclude": "", "include": "", "complexity": "Medium"}	2025-06-20 17:51:51.854205+00	app_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750441911638_2lx2zr754	completed	2025-06-20 17:51:51.854205+00
240c0949-5008-4ace-a475-c403037793ee	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	10	grant	signup_bonus	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 20:49:56.143656+00	\N	completed	2025-06-20 20:49:56.143656+00
23a1470d-8a55-4b91-ae4a-a92b8c5821e1	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-3	consume	Consumed for inspire_generation	c09cb322-bfc7-4330-9bb5-0eaaac98a636	{"dish": "hamburger and fries", "exclude": "", "include": "", "complexity": "Simple"}	2025-06-20 20:53:00.49296+00	app_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750452780205_8a7ln6vvg	completed	2025-06-20 20:53:00.49296+00
a76be022-ef61-4be5-899e-6a7aeff9f57c	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_something_good_for_me	46f666d2-defe-4172-b847-2377caa3449f	{"category": "Something good for me"}	2025-06-20 21:00:40.496853+00	something_good_for_me_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750453240269_1b42lyse5	completed	2025-06-20 21:00:40.496853+00
3f30e3d0-067b-4fcd-b8f4-0e62dc3f2901	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	1	grant	daily_login	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 21:07:13.291452+00	\N	completed	2025-06-20 21:07:13.291452+00
9bbe0387-01d5-481c-ba07-66a3ab2350a9	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_something_nice_for_another	46f666d2-defe-4172-b847-2377caa3449f	{"category": "Something nice for another"}	2025-06-20 22:22:54.841481+00	something_nice_for_another_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750458174524_17thd1dtu	completed	2025-06-20 22:22:54.841481+00
59af0ce0-7111-4056-9dc6-9da46cc0e739	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-3	consume	Consumed for recipe_generation	c09cb322-bfc7-4330-9bb5-0eaaac98a636	{"dish": "tuna sandwich", "exclude": "", "include": "", "complexity": "Simple"}	2025-06-20 22:24:04.863581+00	app_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750458244717_wc69igrly	completed	2025-06-20 22:24:04.863581+00
24fac58f-30e9-48ab-9308-8c251ad550c0	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_a_challenge_to_try	46f666d2-defe-4172-b847-2377caa3449f	{"category": "A challenge to try"}	2025-06-20 22:25:16.051563+00	a_challenge_to_try_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750458315805_nlvkcwfey	completed	2025-06-20 22:25:16.051563+00
974ba977-79d8-4f10-b7d3-4e1d4bd79de5	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_something_good_for_me	46f666d2-defe-4172-b847-2377caa3449f	{"category": "Something good for me"}	2025-06-20 22:30:13.742102+00	something_good_for_me_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750458613463_8khzldnth	completed	2025-06-20 22:30:13.742102+00
12286629-c9a8-43bd-870f-c9cd88d0698c	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	1	grant	profile_question	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 23:07:25.765182+00	\N	completed	2025-06-20 23:07:25.765182+00
7949065d-4579-4cb9-ac7e-361e1610ecef	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	1	grant	profile_question	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 23:07:30.684268+00	\N	completed	2025-06-20 23:07:30.684268+00
cc9b47bd-efe2-4343-986b-45404da93fec	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	1	grant	profile_question	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-20 23:07:34.223564+00	\N	completed	2025-06-20 23:07:34.223564+00
23537569-d7ae-4ad3-88c7-2eb453820503	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-2	consume	Consumed for inspire_a_creative_spark	46f666d2-defe-4172-b847-2377caa3449f	{"category": "A creative spark"}	2025-06-21 01:20:02.379955+00	a_creative_spark_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750468802055_ul2q7dgxy	completed	2025-06-21 01:20:02.379955+00
40c4a461-55d0-43b7-b996-f02ca71ba780	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	-3	consume	Consumed for recipe_generation	c09cb322-bfc7-4330-9bb5-0eaaac98a636	{"dish": "salmon", "exclude": "", "include": "", "complexity": "Simple"}	2025-06-21 01:21:24.7702+00	app_9b061774-85a0-4d5a-9a6a-bb81dc6ac61b_1750468884594_4nnorf6ip	completed	2025-06-21 01:21:24.7702+00
6e990635-c57a-4e71-b41f-c6b0408b5897	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	1	grant	profile_question	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-21 01:36:10.899994+00	\N	completed	2025-06-21 01:36:10.899994+00
ddafec60-181a-4a7a-b515-6a60c0b41e27	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	1	grant	profile_question	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-21 01:38:16.958235+00	\N	completed	2025-06-21 01:38:16.958235+00
82e6d590-7834-4810-8a8b-81c99f0f3381	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	1	grant	profile_question	\N	{"admin_id": "9b061774-85a0-4d5a-9a6a-bb81dc6ac61b"}	2025-06-21 01:45:56.57535+00	\N	completed	2025-06-21 01:45:56.57535+00
\.


--
-- Data for Name: hourly_app_stats; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.hourly_app_stats (app_id, hour, unique_users, transactions, dust_consumed, created_at) FROM stdin;
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-04 23:00:00+00	1	4	8	2025-06-05 01:27:00.25762+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-05 00:00:00+00	1	8	16	2025-06-05 02:27:00.266457+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-05 17:00:00+00	1	1	2	2025-06-05 19:46:50.810955+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-05 18:00:00+00	1	12	24	2025-06-05 20:46:50.817605+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-05 19:00:00+00	1	6	12	2025-06-05 21:46:50.828559+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-11 15:00:00+00	1	1	2	2025-06-11 17:46:51.333395+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-15 23:00:00+00	1	2	4	2025-06-16 01:09:50.11172+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 00:00:00+00	1	2	4	2025-06-16 02:09:50.126939+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 01:00:00+00	1	5	10	2025-06-16 03:09:50.18981+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 02:00:00+00	1	12	24	2025-06-16 04:09:50.194721+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 03:00:00+00	1	4	8	2025-06-16 05:09:50.207895+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 14:00:00+00	1	3	6	2025-06-16 16:09:50.258766+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 15:00:00+00	1	3	6	2025-06-16 17:09:50.439255+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 16:00:00+00	1	3	6	2025-06-16 18:09:50.488799+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 21:00:00+00	1	3	6	2025-06-16 23:09:50.511417+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-16 22:00:00+00	1	4	8	2025-06-17 00:09:50.847569+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-17 15:00:00+00	1	1	2	2025-06-17 17:11:27.3204+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-17 16:00:00+00	1	2	4	2025-06-17 18:11:27.338719+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-17 17:00:00+00	1	1	2	2025-06-17 19:11:27.356068+00
678b9097-6d3b-4f58-9d0f-81f9af551697	2025-06-17 17:00:00+00	1	8	40	2025-06-17 19:11:27.356068+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-18 15:00:00+00	1	1	2	2025-06-18 17:11:28.192418+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-18 17:00:00+00	2	2	4	2025-06-18 19:11:30.972357+00
678b9097-6d3b-4f58-9d0f-81f9af551697	2025-06-18 17:00:00+00	1	2	4	2025-06-18 19:11:30.972357+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-18 21:00:00+00	2	2	4	2025-06-18 23:11:34.484151+00
678b9097-6d3b-4f58-9d0f-81f9af551697	2025-06-18 21:00:00+00	1	1	2	2025-06-18 23:11:34.484151+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-18 23:00:00+00	1	2	4	2025-06-19 01:11:38.608109+00
4c890b06-e8a0-494e-9445-5fad2e1124af	2025-06-19 01:00:00+00	1	2	4	2025-06-19 03:11:38.624362+00
678b9097-6d3b-4f58-9d0f-81f9af551697	2025-06-19 03:00:00+00	1	2	4	2025-06-19 05:11:38.634202+00
46f666d2-defe-4172-b847-2377caa3449f	2025-06-20 15:00:00+00	1	6	12	2025-06-20 17:44:05.097714+00
c09cb322-bfc7-4330-9bb5-0eaaac98a636	2025-06-20 17:00:00+00	1	3	9	2025-06-20 19:44:05.181669+00
c09cb322-bfc7-4330-9bb5-0eaaac98a636	2025-06-20 20:00:00+00	1	1	3	2025-06-20 22:44:08.71416+00
46f666d2-defe-4172-b847-2377caa3449f	2025-06-20 21:00:00+00	1	1	2	2025-06-20 23:44:08.760686+00
46f666d2-defe-4172-b847-2377caa3449f	2025-06-20 22:00:00+00	1	3	6	2025-06-21 00:51:27.488339+00
c09cb322-bfc7-4330-9bb5-0eaaac98a636	2025-06-20 22:00:00+00	1	1	3	2025-06-21 00:51:27.488339+00
46f666d2-defe-4172-b847-2377caa3449f	2025-06-21 01:00:00+00	1	1	2	2025-06-21 03:00:07.100439+00
c09cb322-bfc7-4330-9bb5-0eaaac98a636	2025-06-21 01:00:00+00	1	1	3	2025-06-21 03:00:07.100439+00
\.


--
-- Data for Name: llm_cost_tracking; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.llm_cost_tracking (id, user_id, app_id, tracking_date, tracking_month, total_requests, total_tokens, total_cost_usd, model_usage, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: llm_usage_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.llm_usage_logs (id, user_id, app_id, provider, model_id, prompt_tokens, completion_tokens, total_tokens, cost_usd, latency_ms, prompt_hash, finish_reason, was_fallback, fallback_reason, request_metadata, created_at) FROM stdin;
\.


--
-- Data for Name: people_in_my_life; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.people_in_my_life (id, user_id, name, age_range, relationship, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: person_profile_data; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.person_profile_data (id, person_id, user_id, category, field_name, field_value, confidence_score, source, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: profiling_questions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.profiling_questions (id, category, question_text, question_type, profile_field, priority, app_context, min_app_uses, options, created_at, is_active) FROM stdin;
adventure_level	personality	How adventurous are you?	scale	adventure_level	8	["fairydust-inspire"]	0	{"max": 5, "min": 1, "labels": {"1": "Prefer familiar", "3": "Sometimes try new things", "5": "Always seeking adventure"}}	2025-06-21 03:07:13.887752+00	t
creativity_level	personality	How creative would you say you are?	scale	creativity_level	7	["fairydust-inspire", "fairydust-recipe"]	0	{"max": 5, "min": 1, "labels": {"1": "Practical", "3": "Somewhat creative", "5": "Very creative"}}	2025-06-21 03:07:13.887752+00	t
cooking_skill_level	cooking	How would you describe your cooking skills?	single_choice	cooking_skill_level	6	["fairydust-recipe"]	0	[{"id": "beginner", "label": "Beginner"}, {"id": "intermediate", "label": "Intermediate"}, {"id": "advanced", "label": "Advanced"}, {"id": "expert", "label": "Expert"}]	2025-06-21 03:07:13.887752+00	t
interests_hobbies	interests	What activities do you enjoy in your free time?	multi_select	interests	10	["fairydust-inspire"]	0	[{"id": "cooking", "label": "Cooking"}, {"id": "fitness", "label": "Fitness"}, {"id": "music", "label": "Music"}, {"id": "reading", "label": "Reading"}, {"id": "gaming", "label": "Gaming"}, {"id": "art", "label": "Art & Crafts"}, {"id": "outdoor", "label": "Outdoor Activities"}, {"id": "travel", "label": "Travel"}]	2025-06-21 03:07:13.887752+00	t
dietary_preferences	cooking	Do you follow any specific dietary preferences?	multi_select	dietary_preferences	9	["fairydust-recipe"]	0	[{"id": "none", "label": "No restrictions"}, {"id": "vegetarian", "label": "Vegetarian"}, {"id": "vegan", "label": "Vegan"}, {"id": "gluten_free", "label": "Gluten-free"}, {"id": "dairy_free", "label": "Dairy-free"}, {"id": "keto", "label": "Keto"}, {"id": "paleo", "label": "Paleo"}, {"id": "low_carb", "label": "Low-carb"}]	2025-06-21 03:07:13.887752+00	t
lifestyle_goals	goals	What are your main lifestyle goals?	multi_select	lifestyle_goals	8	["fairydust-inspire"]	0	[{"id": "health", "label": "Health & Wellness"}, {"id": "relationships", "label": "Relationships"}, {"id": "career", "label": "Career Growth"}, {"id": "learning", "label": "Learning & Growth"}, {"id": "creativity", "label": "Creative Expression"}, {"id": "adventure", "label": "Adventure & Travel"}, {"id": "family", "label": "Family Time"}, {"id": "relaxation", "label": "Rest & Relaxation"}]	2025-06-21 03:07:13.887752+00	t
cooking_frequency	cooking	How often do you cook at home?	single_choice	cooking_frequency	7	["fairydust-recipe"]	0	[{"id": "never", "label": "Never"}, {"id": "rarely", "label": "Rarely"}, {"id": "sometimes", "label": "Sometimes"}, {"id": "often", "label": "Often"}, {"id": "daily", "label": "Daily"}]	2025-06-21 03:42:20.117982+00	t
social_preference	personality	What size groups do you prefer for activities?	single_choice	social_preference	5	["fairydust-inspire"]	0	[{"id": "solo", "label": "Solo activities"}, {"id": "small_group", "label": "Small groups (2-4 people)"}, {"id": "large_group", "label": "Large groups (5+ people)"}, {"id": "varies", "label": "Depends on the activity"}]	2025-06-21 03:07:13.887752+00	t
cooking_skill	cooking	How would you describe your cooking skills?	single_choice	cooking_skill	6	["fairydust-recipe"]	0	[{"id": "beginner", "label": "Beginner"}, {"id": "intermediate", "label": "Intermediate"}, {"id": "advanced", "label": "Advanced"}, {"id": "expert", "label": "Expert"}]	2025-06-21 06:38:10.936241+00	t
\.


--
-- Data for Name: user_auth_providers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_auth_providers (user_id, provider, provider_user_id, created_at) FROM stdin;
\.


--
-- Data for Name: user_profile_data; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_profile_data (id, user_id, category, field_name, field_value, confidence_score, source, app_context, created_at, updated_at) FROM stdin;
5f31b380-6412-4af0-bf85-b570b64c90b5	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	cooking	cooking_skill	"intermediate"	1	user_input	\N	2025-06-21 05:14:34.237866+00	2025-06-21 05:59:14.429465+00
8333c637-c7f1-4242-adfd-60e2ea898f60	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	interests	interests	["cooking", "music", "gaming"]	1	user_input	\N	2025-06-21 05:29:18.777985+00	2025-06-21 06:11:48.978305+00
06aef3a4-dccc-43ff-85aa-f51d0d3e2482	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	cooking	dietary_preferences	["vegan", "dairy_free", "paleo"]	1	user_input	\N	2025-06-21 05:29:22.050876+00	2025-06-21 06:11:49.234208+00
1c5d3e64-ff65-4de8-ac16-3eb0f649bbe5	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	goals	lifestyle_goals	["relationships", "career", "creativity"]	1	user_input	\N	2025-06-21 05:29:23.290244+00	2025-06-21 06:11:50.174081+00
c32cc7fc-d4be-48d0-8fab-85b59ee60ece	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	personality	adventure_level	4	1	user_input	\N	2025-06-21 05:11:53.151564+00	2025-06-21 06:11:53.164272+00
406f7100-80ee-4898-8ee7-011c5793716b	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	cooking	cooking_frequency	"daily"	1	user_input	\N	2025-06-21 05:11:59.806576+00	2025-06-21 06:11:54.126578+00
e7abe050-b135-4870-9ed9-920327b6c59e	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	personality	creativity_level	5	1	user_input	\N	2025-06-21 05:14:32.392603+00	2025-06-21 06:12:02.791425+00
a3de7e1b-f069-41fd-997a-89504588e3a9	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	cooking	cooking_skill_level	"advanced"	1	user_input	\N	2025-06-21 05:37:35.270409+00	2025-06-21 06:12:03.636669+00
498ecdb6-7bb5-4ab3-85d2-2a52a267c6e1	9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	personality	social_preference	"small_group"	1	user_input	\N	2025-06-21 05:14:37.5296+00	2025-06-21 06:12:03.706443+00
\.


--
-- Data for Name: user_question_responses; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_question_responses (id, user_id, question_id, response_value, session_id, dust_reward, answered_at) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, fairyname, email, phone, avatar_url, is_builder, is_active, dust_balance, auth_provider, created_at, updated_at, is_admin, last_name, first_name, age_range, city, country, last_profiling_session, total_profiling_sessions) FROM stdin;
d40d539a-9124-4a78-9589-b00f0b89b17f	stellardream5887	Callingjen27@yahoo.com	\N	\N	f	t	72	otp	2025-06-18 23:17:17.894+00	2025-06-19 01:43:07.023+00	f	\N	\N	\N	\N	US	\N	0
3f40b36f-c600-4075-8974-3f6c5f21f557	crystaldusk6193	Cicilycastillo@me.com	\N	\N	f	t	100	otp	2025-06-11 15:50:03.969+00	2025-06-11 15:50:11.653+00	f	\N	\N	\N	\N	US	\N	0
9b061774-85a0-4d5a-9a6a-bb81dc6ac61b	stellardawn2947	damonw@gmail.com	\N	\N	f	t	154	otp	2025-06-04 21:55:47.728+00	2025-06-21 01:45:56.57535+00	t	\N	Bobb	35-44	aaa	US	2025-06-21 06:12:02.823915	45
6d9d7423-3c9b-4c97-b97e-7fdb275aa789	twilightspark7090	damon@greenwork.ai	\N	\N	f	t	23	otp	2025-06-18 17:40:35.344982+00	2025-06-18 17:41:01.719669+00	f	\N	\N	\N	\N	US	\N	0
6ff1f86a-5b22-49d3-8785-247780e2e2cf	twilightdusk8748	jennyhedemark27@gmail.com	\N	\N	f	t	23	otp	2025-06-18 21:54:01.430444+00	2025-06-18 21:54:05.903637+00	f	\N	\N	\N	\N	US	\N	0
\.


--
-- Name: app_model_configs app_model_configs_app_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.app_model_configs
    ADD CONSTRAINT app_model_configs_app_id_key UNIQUE (app_id);


--
-- Name: app_model_configs app_model_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.app_model_configs
    ADD CONSTRAINT app_model_configs_pkey PRIMARY KEY (id);


--
-- Name: apps apps_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apps
    ADD CONSTRAINT apps_pkey PRIMARY KEY (id);


--
-- Name: apps apps_slug_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apps
    ADD CONSTRAINT apps_slug_key UNIQUE (slug);


--
-- Name: dust_transactions dust_transactions_idempotency_key_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dust_transactions
    ADD CONSTRAINT dust_transactions_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: dust_transactions dust_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dust_transactions
    ADD CONSTRAINT dust_transactions_pkey PRIMARY KEY (id);


--
-- Name: hourly_app_stats hourly_app_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hourly_app_stats
    ADD CONSTRAINT hourly_app_stats_pkey PRIMARY KEY (app_id, hour);


--
-- Name: llm_cost_tracking llm_cost_tracking_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.llm_cost_tracking
    ADD CONSTRAINT llm_cost_tracking_pkey PRIMARY KEY (id);


--
-- Name: llm_cost_tracking llm_cost_tracking_user_id_app_id_tracking_date_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.llm_cost_tracking
    ADD CONSTRAINT llm_cost_tracking_user_id_app_id_tracking_date_key UNIQUE (user_id, app_id, tracking_date);


--
-- Name: llm_usage_logs llm_usage_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.llm_usage_logs
    ADD CONSTRAINT llm_usage_logs_pkey PRIMARY KEY (id);


--
-- Name: people_in_my_life people_in_my_life_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.people_in_my_life
    ADD CONSTRAINT people_in_my_life_pkey PRIMARY KEY (id);


--
-- Name: person_profile_data person_profile_data_person_id_field_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.person_profile_data
    ADD CONSTRAINT person_profile_data_person_id_field_name_key UNIQUE (person_id, field_name);


--
-- Name: person_profile_data person_profile_data_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.person_profile_data
    ADD CONSTRAINT person_profile_data_pkey PRIMARY KEY (id);


--
-- Name: profiling_questions profiling_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.profiling_questions
    ADD CONSTRAINT profiling_questions_pkey PRIMARY KEY (id);


--
-- Name: user_auth_providers user_auth_providers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_auth_providers
    ADD CONSTRAINT user_auth_providers_pkey PRIMARY KEY (user_id, provider);


--
-- Name: user_profile_data user_profile_data_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_profile_data
    ADD CONSTRAINT user_profile_data_pkey PRIMARY KEY (id);


--
-- Name: user_profile_data user_profile_data_user_id_field_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_profile_data
    ADD CONSTRAINT user_profile_data_user_id_field_name_key UNIQUE (user_id, field_name);


--
-- Name: user_question_responses user_question_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_question_responses
    ADD CONSTRAINT user_question_responses_pkey PRIMARY KEY (id);


--
-- Name: user_question_responses user_question_responses_user_id_question_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_question_responses
    ADD CONSTRAINT user_question_responses_user_id_question_id_key UNIQUE (user_id, question_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_fairyname_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_fairyname_key UNIQUE (fairyname);


--
-- Name: users users_phone_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_phone_key UNIQUE (phone);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_app_model_configs_app_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_app_model_configs_app_id ON public.app_model_configs USING btree (app_id);


--
-- Name: idx_apps_active_approved; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apps_active_approved ON public.apps USING btree (is_active, is_approved);


--
-- Name: idx_apps_builder; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apps_builder ON public.apps USING btree (builder_id);


--
-- Name: idx_apps_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apps_category ON public.apps USING btree (category);


--
-- Name: idx_apps_registered_by_service; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apps_registered_by_service ON public.apps USING btree (registered_by_service);


--
-- Name: idx_apps_registration_source; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apps_registration_source ON public.apps USING btree (registration_source);


--
-- Name: idx_apps_slug; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apps_slug ON public.apps USING btree (slug);


--
-- Name: idx_apps_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apps_status ON public.apps USING btree (status);


--
-- Name: idx_auth_providers_lookup; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_auth_providers_lookup ON public.user_auth_providers USING btree (provider, provider_user_id);


--
-- Name: idx_dust_transactions_app; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_dust_transactions_app ON public.dust_transactions USING btree (app_id, created_at DESC);


--
-- Name: idx_dust_transactions_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_dust_transactions_user ON public.dust_transactions USING btree (user_id, created_at DESC);


--
-- Name: idx_dust_tx_idempotency; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_dust_tx_idempotency ON public.dust_transactions USING btree (idempotency_key) WHERE (idempotency_key IS NOT NULL);


--
-- Name: idx_dust_tx_pending; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_dust_tx_pending ON public.dust_transactions USING btree (status, created_at) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_dust_tx_user_type_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_dust_tx_user_type_created ON public.dust_transactions USING btree (user_id, type, created_at DESC);


--
-- Name: idx_hourly_stats_hour; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_hourly_stats_hour ON public.hourly_app_stats USING btree (hour DESC);


--
-- Name: idx_llm_cost_tracking_app_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_llm_cost_tracking_app_date ON public.llm_cost_tracking USING btree (app_id, tracking_date);


--
-- Name: idx_llm_cost_tracking_month; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_llm_cost_tracking_month ON public.llm_cost_tracking USING btree (tracking_month);


--
-- Name: idx_llm_cost_tracking_user_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_llm_cost_tracking_user_date ON public.llm_cost_tracking USING btree (user_id, tracking_date);


--
-- Name: idx_llm_usage_logs_app_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_llm_usage_logs_app_id ON public.llm_usage_logs USING btree (app_id);


--
-- Name: idx_llm_usage_logs_cost; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_llm_usage_logs_cost ON public.llm_usage_logs USING btree (cost_usd);


--
-- Name: idx_llm_usage_logs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_llm_usage_logs_created_at ON public.llm_usage_logs USING btree (created_at);


--
-- Name: idx_llm_usage_logs_provider_model; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_llm_usage_logs_provider_model ON public.llm_usage_logs USING btree (provider, model_id);


--
-- Name: idx_llm_usage_logs_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_llm_usage_logs_user_id ON public.llm_usage_logs USING btree (user_id);


--
-- Name: idx_people_in_my_life_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_people_in_my_life_user_id ON public.people_in_my_life USING btree (user_id);


--
-- Name: idx_person_profile_data_person_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_person_profile_data_person_id ON public.person_profile_data USING btree (person_id);


--
-- Name: idx_person_profile_data_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_person_profile_data_user_id ON public.person_profile_data USING btree (user_id);


--
-- Name: idx_profiling_questions_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_profiling_questions_category ON public.profiling_questions USING btree (category);


--
-- Name: idx_profiling_questions_priority; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_profiling_questions_priority ON public.profiling_questions USING btree (priority);


--
-- Name: idx_user_profile_data_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_profile_data_category ON public.user_profile_data USING btree (category);


--
-- Name: idx_user_profile_data_composite; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_profile_data_composite ON public.user_profile_data USING btree (user_id, category, field_name);


--
-- Name: idx_user_profile_data_field_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_profile_data_field_name ON public.user_profile_data USING btree (field_name);


--
-- Name: idx_user_profile_data_updated_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_profile_data_updated_at ON public.user_profile_data USING btree (updated_at);


--
-- Name: idx_user_profile_data_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_profile_data_user_id ON public.user_profile_data USING btree (user_id);


--
-- Name: idx_user_question_responses_question_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_question_responses_question_id ON public.user_question_responses USING btree (question_id);


--
-- Name: idx_user_question_responses_session; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_question_responses_session ON public.user_question_responses USING btree (session_id);


--
-- Name: idx_user_question_responses_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_question_responses_user_id ON public.user_question_responses USING btree (user_id);


--
-- Name: idx_users_admin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_users_admin ON public.users USING btree (is_admin) WHERE (is_admin = true);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_fairyname; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_users_fairyname ON public.users USING btree (fairyname);


--
-- Name: idx_users_phone; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_users_phone ON public.users USING btree (phone);


--
-- Name: app_model_configs app_model_configs_app_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.app_model_configs
    ADD CONSTRAINT app_model_configs_app_id_fkey FOREIGN KEY (app_id) REFERENCES public.apps(id) ON DELETE CASCADE;


--
-- Name: apps apps_builder_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apps
    ADD CONSTRAINT apps_builder_id_fkey FOREIGN KEY (builder_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: dust_transactions dust_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.dust_transactions
    ADD CONSTRAINT dust_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: hourly_app_stats hourly_app_stats_app_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hourly_app_stats
    ADD CONSTRAINT hourly_app_stats_app_id_fkey FOREIGN KEY (app_id) REFERENCES public.apps(id) ON DELETE CASCADE;


--
-- Name: llm_cost_tracking llm_cost_tracking_app_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.llm_cost_tracking
    ADD CONSTRAINT llm_cost_tracking_app_id_fkey FOREIGN KEY (app_id) REFERENCES public.apps(id) ON DELETE CASCADE;


--
-- Name: llm_cost_tracking llm_cost_tracking_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.llm_cost_tracking
    ADD CONSTRAINT llm_cost_tracking_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: llm_usage_logs llm_usage_logs_app_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.llm_usage_logs
    ADD CONSTRAINT llm_usage_logs_app_id_fkey FOREIGN KEY (app_id) REFERENCES public.apps(id) ON DELETE CASCADE;


--
-- Name: llm_usage_logs llm_usage_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.llm_usage_logs
    ADD CONSTRAINT llm_usage_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: people_in_my_life people_in_my_life_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.people_in_my_life
    ADD CONSTRAINT people_in_my_life_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: person_profile_data person_profile_data_person_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.person_profile_data
    ADD CONSTRAINT person_profile_data_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.people_in_my_life(id) ON DELETE CASCADE;


--
-- Name: person_profile_data person_profile_data_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.person_profile_data
    ADD CONSTRAINT person_profile_data_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_auth_providers user_auth_providers_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_auth_providers
    ADD CONSTRAINT user_auth_providers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_profile_data user_profile_data_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_profile_data
    ADD CONSTRAINT user_profile_data_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_question_responses user_question_responses_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_question_responses
    ADD CONSTRAINT user_question_responses_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.profiling_questions(id);


--
-- Name: user_question_responses user_question_responses_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_question_responses
    ADD CONSTRAINT user_question_responses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

