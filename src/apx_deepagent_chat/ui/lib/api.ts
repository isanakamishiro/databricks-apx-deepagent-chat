import { useQuery, useSuspenseQuery, useMutation } from "@tanstack/react-query";
import type { UseQueryOptions, UseSuspenseQueryOptions, UseMutationOptions } from "@tanstack/react-query";
export class ApiError extends Error {
    status: number;
    statusText: string;
    body: unknown;
    constructor(status: number, statusText: string, body: unknown){
        super(`HTTP ${status}: ${statusText}`);
        this.name = "ApiError";
        this.status = status;
        this.statusText = statusText;
        this.body = body;
    }
}
export interface ApproveDecision {
    message?: string | null;
    type: "approve" | "reject";
}
export interface Body_filesUpload {
    file: string;
    path: string;
}
export interface Body_filesUploadAttachment {
    file: string;
}
export interface CatalogOut {
    name: string;
}
export interface ChatApproveRequest {
    decisions: ApproveDecision[];
}
export interface ChatApproveResponse {
    ok: boolean;
}
export interface ChatInterruptResponse {
    ok: boolean;
}
export interface ChatStartResponse {
    job_id: string;
}
export interface ComplexValue {
    display?: string | null;
    primary?: boolean | null;
    ref?: string | null;
    type?: string | null;
    value?: string | null;
}
export interface HTTPValidationError {
    detail?: ValidationError[];
}
export interface MkdirRequest {
    path: string;
}
export interface Name {
    family_name?: string | null;
    given_name?: string | null;
}
export interface SaveChatRequest {
    createdAt: string;
    id: string;
    title: string;
    userId: string;
    visibility?: string;
}
export interface SaveMessagesRequest {
    messages: Record<string, unknown>[];
    userId: string;
}
export interface SchemaOut {
    name: string;
}
export interface ThreadStateResponse {
    messages: Record<string, unknown>[];
    status: "interrupted" | "completed" | "not_found";
}
export interface UploadAttachmentResponse {
    ok: boolean;
    path: string;
}
export interface User {
    active?: boolean | null;
    display_name?: string | null;
    emails?: ComplexValue[] | null;
    entitlements?: ComplexValue[] | null;
    external_id?: string | null;
    groups?: ComplexValue[] | null;
    id?: string | null;
    name?: Name | null;
    roles?: ComplexValue[] | null;
    schemas?: UserSchema[] | null;
    user_name?: string | null;
}
export const UserSchema = {
    "urn:ietf:params:scim:schemas:core:2.0:User": "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:workspace:2.0:User": "urn:ietf:params:scim:schemas:extension:workspace:2.0:User"
} as const;
export type UserSchema = typeof UserSchema[keyof typeof UserSchema];
export interface ValidationError {
    ctx?: Record<string, unknown>;
    input?: unknown;
    loc: (string | number)[];
    msg: string;
    type: string;
}
export interface VersionOut {
    version: string;
}
export interface VolumeOut {
    name: string;
}
export interface VolumeValidateOut {
    exists: boolean;
}
export const agent_info_endpoint_agent_info_get = async (options?: RequestInit): Promise<{
    data: Record<string, unknown>;
}> =>{
    const res = await fetch("/agent/info", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const agent_info_endpoint_agent_info_getKey = ()=>{
    return [
        "/agent/info"
    ] as const;
};
export function useAgent_info_endpoint_agent_info_get<TData = {
    data: Record<string, unknown>;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: Record<string, unknown>;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: agent_info_endpoint_agent_info_getKey(),
        queryFn: ()=>agent_info_endpoint_agent_info_get(),
        ...options?.query
    });
}
export function useAgent_info_endpoint_agent_info_getSuspense<TData = {
    data: Record<string, unknown>;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: Record<string, unknown>;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: agent_info_endpoint_agent_info_getKey(),
        queryFn: ()=>agent_info_endpoint_agent_info_get(),
        ...options?.query
    });
}
export interface ListChatsParams {
    user_id: string;
    limit?: number;
    ending_before?: string | null;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const listChats = async (params: ListChatsParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.user_id != null) searchParams.set("user_id", String(params.user_id));
    if (params?.limit != null) searchParams.set("limit", String(params?.limit));
    if (params?.ending_before != null) searchParams.set("ending_before", String(params?.ending_before));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat-history?${queryString}` : "/api/chat-history";
    const res = await fetch(url, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const listChatsKey = (params?: ListChatsParams)=>{
    return [
        "/api/chat-history",
        params
    ] as const;
};
export function useListChats<TData = {
    data: unknown;
}>(options: {
    params: ListChatsParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: listChatsKey(options.params),
        queryFn: ()=>listChats(options.params),
        ...options?.query
    });
}
export function useListChatsSuspense<TData = {
    data: unknown;
}>(options: {
    params: ListChatsParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: listChatsKey(options.params),
        queryFn: ()=>listChats(options.params),
        ...options?.query
    });
}
export interface SaveChatParams {
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const saveChat = async (data: SaveChatRequest, params?: SaveChatParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/chat-history", {
        ...options,
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useSaveChat(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: SaveChatParams;
        data: SaveChatRequest;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>saveChat(vars.data, vars.params),
        ...options?.mutation
    });
}
export interface GetChatParams {
    chat_id: string;
    user_id: string;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const getChat = async (params: GetChatParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.user_id != null) searchParams.set("user_id", String(params.user_id));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat-history/${params.chat_id}?${queryString}` : `/api/chat-history/${params.chat_id}`;
    const res = await fetch(url, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const getChatKey = (params?: GetChatParams)=>{
    return [
        "/api/chat-history/{chat_id}",
        params
    ] as const;
};
export function useGetChat<TData = {
    data: unknown;
}>(options: {
    params: GetChatParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: getChatKey(options.params),
        queryFn: ()=>getChat(options.params),
        ...options?.query
    });
}
export function useGetChatSuspense<TData = {
    data: unknown;
}>(options: {
    params: GetChatParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: getChatKey(options.params),
        queryFn: ()=>getChat(options.params),
        ...options?.query
    });
}
export interface DeleteChatParams {
    chat_id: string;
    user_id: string;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const deleteChat = async (params: DeleteChatParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.user_id != null) searchParams.set("user_id", String(params.user_id));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat-history/${params.chat_id}?${queryString}` : `/api/chat-history/${params.chat_id}`;
    const res = await fetch(url, {
        ...options,
        method: "DELETE",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useDeleteChat(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: DeleteChatParams;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>deleteChat(vars.params),
        ...options?.mutation
    });
}
export interface GetMessagesParams {
    chat_id: string;
    user_id: string;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const getMessages = async (params: GetMessagesParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.user_id != null) searchParams.set("user_id", String(params.user_id));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat-history/${params.chat_id}/messages?${queryString}` : `/api/chat-history/${params.chat_id}/messages`;
    const res = await fetch(url, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const getMessagesKey = (params?: GetMessagesParams)=>{
    return [
        "/api/chat-history/{chat_id}/messages",
        params
    ] as const;
};
export function useGetMessages<TData = {
    data: unknown;
}>(options: {
    params: GetMessagesParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: getMessagesKey(options.params),
        queryFn: ()=>getMessages(options.params),
        ...options?.query
    });
}
export function useGetMessagesSuspense<TData = {
    data: unknown;
}>(options: {
    params: GetMessagesParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: getMessagesKey(options.params),
        queryFn: ()=>getMessages(options.params),
        ...options?.query
    });
}
export interface SaveMessagesParams {
    chat_id: string;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const saveMessages = async (params: SaveMessagesParams, data: SaveMessagesRequest, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch(`/api/chat-history/${params.chat_id}/messages`, {
        ...options,
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useSaveMessages(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: SaveMessagesParams;
        data: SaveMessagesRequest;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>saveMessages(vars.params, vars.data),
        ...options?.mutation
    });
}
export interface ChatApproveParams {
    job_id: string;
}
export const chatApprove = async (params: ChatApproveParams, data: ChatApproveRequest, options?: RequestInit): Promise<{
    data: ChatApproveResponse;
}> =>{
    const res = await fetch(`/api/chat/approve/${params.job_id}`, {
        ...options,
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...options?.headers
        },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useChatApprove(options?: {
    mutation?: UseMutationOptions<{
        data: ChatApproveResponse;
    }, ApiError, {
        params: ChatApproveParams;
        data: ChatApproveRequest;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>chatApprove(vars.params, vars.data),
        ...options?.mutation
    });
}
export interface ChatInterruptParams {
    job_id: string;
    deep?: boolean;
}
export const chatInterrupt = async (params: ChatInterruptParams, options?: RequestInit): Promise<{
    data: ChatInterruptResponse;
}> =>{
    const searchParams = new URLSearchParams();
    if (params?.deep != null) searchParams.set("deep", String(params?.deep));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/chat/interrupt/${params.job_id}?${queryString}` : `/api/chat/interrupt/${params.job_id}`;
    const res = await fetch(url, {
        ...options,
        method: "POST"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useChatInterrupt(options?: {
    mutation?: UseMutationOptions<{
        data: ChatInterruptResponse;
    }, ApiError, {
        params: ChatInterruptParams;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>chatInterrupt(vars.params),
        ...options?.mutation
    });
}
export interface ChatStartParams {
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const chatStart = async (params?: ChatStartParams, options?: RequestInit): Promise<{
    data: ChatStartResponse;
}> =>{
    const res = await fetch("/api/chat/start", {
        ...options,
        method: "POST",
        headers: {
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useChatStart(options?: {
    mutation?: UseMutationOptions<{
        data: ChatStartResponse;
    }, ApiError, {
        params: ChatStartParams;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>chatStart(vars.params),
        ...options?.mutation
    });
}
export interface Chat_stream_api_chat_stream__job_id__getParams {
    job_id: string;
}
export const chat_stream_api_chat_stream__job_id__get = async (params: Chat_stream_api_chat_stream__job_id__getParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch(`/api/chat/stream/${params.job_id}`, {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const chat_stream_api_chat_stream__job_id__getKey = (params?: Chat_stream_api_chat_stream__job_id__getParams)=>{
    return [
        "/api/chat/stream/{job_id}",
        params
    ] as const;
};
export function useChat_stream_api_chat_stream__job_id__get<TData = {
    data: unknown;
}>(options: {
    params: Chat_stream_api_chat_stream__job_id__getParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: chat_stream_api_chat_stream__job_id__getKey(options.params),
        queryFn: ()=>chat_stream_api_chat_stream__job_id__get(options.params),
        ...options?.query
    });
}
export function useChat_stream_api_chat_stream__job_id__getSuspense<TData = {
    data: unknown;
}>(options: {
    params: Chat_stream_api_chat_stream__job_id__getParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: chat_stream_api_chat_stream__job_id__getKey(options.params),
        queryFn: ()=>chat_stream_api_chat_stream__job_id__get(options.params),
        ...options?.query
    });
}
export interface ChatThreadStateParams {
    thread_id: string;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const chatThreadState = async (params: ChatThreadStateParams, options?: RequestInit): Promise<{
    data: ThreadStateResponse;
}> =>{
    const res = await fetch(`/api/chat/thread/${params.thread_id}/state`, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const chatThreadStateKey = (params?: ChatThreadStateParams)=>{
    return [
        "/api/chat/thread/{thread_id}/state",
        params
    ] as const;
};
export function useChatThreadState<TData = {
    data: ThreadStateResponse;
}>(options: {
    params: ChatThreadStateParams;
    query?: Omit<UseQueryOptions<{
        data: ThreadStateResponse;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: chatThreadStateKey(options.params),
        queryFn: ()=>chatThreadState(options.params),
        ...options?.query
    });
}
export function useChatThreadStateSuspense<TData = {
    data: ThreadStateResponse;
}>(options: {
    params: ChatThreadStateParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: ThreadStateResponse;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: chatThreadStateKey(options.params),
        queryFn: ()=>chatThreadState(options.params),
        ...options?.query
    });
}
export const getConfig = async (options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/config", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const getConfigKey = ()=>{
    return [
        "/api/config"
    ] as const;
};
export function useGetConfig<TData = {
    data: unknown;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: getConfigKey(),
        queryFn: ()=>getConfig(),
        ...options?.query
    });
}
export function useGetConfigSuspense<TData = {
    data: unknown;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: getConfigKey(),
        queryFn: ()=>getConfig(),
        ...options?.query
    });
}
export interface CurrentUserParams {
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const currentUser = async (params?: CurrentUserParams, options?: RequestInit): Promise<{
    data: User;
}> =>{
    const res = await fetch("/api/current-user", {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const currentUserKey = (params?: CurrentUserParams)=>{
    return [
        "/api/current-user",
        params
    ] as const;
};
export function useCurrentUser<TData = {
    data: User;
}>(options?: {
    params?: CurrentUserParams;
    query?: Omit<UseQueryOptions<{
        data: User;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: currentUserKey(options?.params),
        queryFn: ()=>currentUser(options?.params),
        ...options?.query
    });
}
export function useCurrentUserSuspense<TData = {
    data: User;
}>(options?: {
    params?: CurrentUserParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: User;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: currentUserKey(options?.params),
        queryFn: ()=>currentUser(options?.params),
        ...options?.query
    });
}
export interface FilesDeleteParams {
    path: string;
    is_dir?: boolean;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const filesDelete = async (params: FilesDeleteParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.path != null) searchParams.set("path", String(params.path));
    if (params?.is_dir != null) searchParams.set("is_dir", String(params?.is_dir));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/files/delete?${queryString}` : "/api/files/delete";
    const res = await fetch(url, {
        ...options,
        method: "DELETE",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useFilesDelete(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: FilesDeleteParams;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>filesDelete(vars.params),
        ...options?.mutation
    });
}
export interface FilesDownloadParams {
    path: string;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const filesDownload = async (params: FilesDownloadParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.path != null) searchParams.set("path", String(params.path));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/files/download?${queryString}` : "/api/files/download";
    const res = await fetch(url, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const filesDownloadKey = (params?: FilesDownloadParams)=>{
    return [
        "/api/files/download",
        params
    ] as const;
};
export function useFilesDownload<TData = {
    data: unknown;
}>(options: {
    params: FilesDownloadParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: filesDownloadKey(options.params),
        queryFn: ()=>filesDownload(options.params),
        ...options?.query
    });
}
export function useFilesDownloadSuspense<TData = {
    data: unknown;
}>(options: {
    params: FilesDownloadParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: filesDownloadKey(options.params),
        queryFn: ()=>filesDownload(options.params),
        ...options?.query
    });
}
export interface FilesListParams {
    path?: string;
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const filesList = async (params?: FilesListParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const searchParams = new URLSearchParams();
    if (params?.path != null) searchParams.set("path", String(params?.path));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/files/list?${queryString}` : "/api/files/list";
    const res = await fetch(url, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const filesListKey = (params?: FilesListParams)=>{
    return [
        "/api/files/list",
        params
    ] as const;
};
export function useFilesList<TData = {
    data: unknown;
}>(options?: {
    params?: FilesListParams;
    query?: Omit<UseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: filesListKey(options?.params),
        queryFn: ()=>filesList(options?.params),
        ...options?.query
    });
}
export function useFilesListSuspense<TData = {
    data: unknown;
}>(options?: {
    params?: FilesListParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: unknown;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: filesListKey(options?.params),
        queryFn: ()=>filesList(options?.params),
        ...options?.query
    });
}
export interface FilesMkdirParams {
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const filesMkdir = async (data: MkdirRequest, params?: FilesMkdirParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/files/mkdir", {
        ...options,
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useFilesMkdir(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: FilesMkdirParams;
        data: MkdirRequest;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>filesMkdir(vars.data, vars.params),
        ...options?.mutation
    });
}
export interface FilesUploadParams {
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const filesUpload = async (data: FormData, params?: FilesUploadParams, options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/api/files/upload", {
        ...options,
        method: "POST",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        },
        body: data
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useFilesUpload(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, {
        params: FilesUploadParams;
        data: FormData;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>filesUpload(vars.data, vars.params),
        ...options?.mutation
    });
}
export interface FilesUploadAttachmentParams {
    "x-uc-volume-path"?: string | null;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const filesUploadAttachment = async (data: FormData, params?: FilesUploadAttachmentParams, options?: RequestInit): Promise<{
    data: UploadAttachmentResponse;
}> =>{
    const res = await fetch("/api/files/upload-attachment", {
        ...options,
        method: "POST",
        headers: {
            ...(params?.["x-uc-volume-path"] != null && {
                "x-uc-volume-path": params["x-uc-volume-path"]
            }),
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        },
        body: data
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useFilesUploadAttachment(options?: {
    mutation?: UseMutationOptions<{
        data: UploadAttachmentResponse;
    }, ApiError, {
        params: FilesUploadAttachmentParams;
        data: FormData;
    }>;
}) {
    return useMutation({
        mutationFn: (vars)=>filesUploadAttachment(vars.data, vars.params),
        ...options?.mutation
    });
}
export const version = async (options?: RequestInit): Promise<{
    data: VersionOut;
}> =>{
    const res = await fetch("/api/version", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const versionKey = ()=>{
    return [
        "/api/version"
    ] as const;
};
export function useVersion<TData = {
    data: VersionOut;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: VersionOut;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: versionKey(),
        queryFn: ()=>version(),
        ...options?.query
    });
}
export function useVersionSuspense<TData = {
    data: VersionOut;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: VersionOut;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: versionKey(),
        queryFn: ()=>version(),
        ...options?.query
    });
}
export interface ListCatalogsParams {
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const listCatalogs = async (params?: ListCatalogsParams, options?: RequestInit): Promise<{
    data: CatalogOut[];
}> =>{
    const res = await fetch("/api/volumes/catalogs", {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const listCatalogsKey = (params?: ListCatalogsParams)=>{
    return [
        "/api/volumes/catalogs",
        params
    ] as const;
};
export function useListCatalogs<TData = {
    data: CatalogOut[];
}>(options?: {
    params?: ListCatalogsParams;
    query?: Omit<UseQueryOptions<{
        data: CatalogOut[];
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: listCatalogsKey(options?.params),
        queryFn: ()=>listCatalogs(options?.params),
        ...options?.query
    });
}
export function useListCatalogsSuspense<TData = {
    data: CatalogOut[];
}>(options?: {
    params?: ListCatalogsParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: CatalogOut[];
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: listCatalogsKey(options?.params),
        queryFn: ()=>listCatalogs(options?.params),
        ...options?.query
    });
}
export interface ListSchemasParams {
    catalog: string;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const listSchemas = async (params: ListSchemasParams, options?: RequestInit): Promise<{
    data: SchemaOut[];
}> =>{
    const searchParams = new URLSearchParams();
    if (params.catalog != null) searchParams.set("catalog", String(params.catalog));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/volumes/schemas?${queryString}` : "/api/volumes/schemas";
    const res = await fetch(url, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const listSchemasKey = (params?: ListSchemasParams)=>{
    return [
        "/api/volumes/schemas",
        params
    ] as const;
};
export function useListSchemas<TData = {
    data: SchemaOut[];
}>(options: {
    params: ListSchemasParams;
    query?: Omit<UseQueryOptions<{
        data: SchemaOut[];
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: listSchemasKey(options.params),
        queryFn: ()=>listSchemas(options.params),
        ...options?.query
    });
}
export function useListSchemasSuspense<TData = {
    data: SchemaOut[];
}>(options: {
    params: ListSchemasParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: SchemaOut[];
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: listSchemasKey(options.params),
        queryFn: ()=>listSchemas(options.params),
        ...options?.query
    });
}
export interface ValidateVolumeParams {
    catalog: string;
    schema: string;
    volume: string;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const validateVolume = async (params: ValidateVolumeParams, options?: RequestInit): Promise<{
    data: VolumeValidateOut;
}> =>{
    const searchParams = new URLSearchParams();
    if (params.catalog != null) searchParams.set("catalog", String(params.catalog));
    if (params.schema != null) searchParams.set("schema", String(params.schema));
    if (params.volume != null) searchParams.set("volume", String(params.volume));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/volumes/validate?${queryString}` : "/api/volumes/validate";
    const res = await fetch(url, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const validateVolumeKey = (params?: ValidateVolumeParams)=>{
    return [
        "/api/volumes/validate",
        params
    ] as const;
};
export function useValidateVolume<TData = {
    data: VolumeValidateOut;
}>(options: {
    params: ValidateVolumeParams;
    query?: Omit<UseQueryOptions<{
        data: VolumeValidateOut;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: validateVolumeKey(options.params),
        queryFn: ()=>validateVolume(options.params),
        ...options?.query
    });
}
export function useValidateVolumeSuspense<TData = {
    data: VolumeValidateOut;
}>(options: {
    params: ValidateVolumeParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: VolumeValidateOut;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: validateVolumeKey(options.params),
        queryFn: ()=>validateVolume(options.params),
        ...options?.query
    });
}
export interface ListVolumesParams {
    catalog: string;
    schema: string;
    "X-Forwarded-Host"?: string | null;
    "X-Forwarded-Preferred-Username"?: string | null;
    "X-Forwarded-User"?: string | null;
    "X-Forwarded-Email"?: string | null;
    "X-Request-Id"?: string | null;
    "X-Forwarded-Access-Token"?: string | null;
}
export const listVolumes = async (params: ListVolumesParams, options?: RequestInit): Promise<{
    data: VolumeOut[];
}> =>{
    const searchParams = new URLSearchParams();
    if (params.catalog != null) searchParams.set("catalog", String(params.catalog));
    if (params.schema != null) searchParams.set("schema", String(params.schema));
    const queryString = searchParams.toString();
    const url = queryString ? `/api/volumes/volumes?${queryString}` : "/api/volumes/volumes";
    const res = await fetch(url, {
        ...options,
        method: "GET",
        headers: {
            ...(params?.["X-Forwarded-Host"] != null && {
                "X-Forwarded-Host": params["X-Forwarded-Host"]
            }),
            ...(params?.["X-Forwarded-Preferred-Username"] != null && {
                "X-Forwarded-Preferred-Username": params["X-Forwarded-Preferred-Username"]
            }),
            ...(params?.["X-Forwarded-User"] != null && {
                "X-Forwarded-User": params["X-Forwarded-User"]
            }),
            ...(params?.["X-Forwarded-Email"] != null && {
                "X-Forwarded-Email": params["X-Forwarded-Email"]
            }),
            ...(params?.["X-Request-Id"] != null && {
                "X-Request-Id": params["X-Request-Id"]
            }),
            ...(params?.["X-Forwarded-Access-Token"] != null && {
                "X-Forwarded-Access-Token": params["X-Forwarded-Access-Token"]
            }),
            ...options?.headers
        }
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const listVolumesKey = (params?: ListVolumesParams)=>{
    return [
        "/api/volumes/volumes",
        params
    ] as const;
};
export function useListVolumes<TData = {
    data: VolumeOut[];
}>(options: {
    params: ListVolumesParams;
    query?: Omit<UseQueryOptions<{
        data: VolumeOut[];
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: listVolumesKey(options.params),
        queryFn: ()=>listVolumes(options.params),
        ...options?.query
    });
}
export function useListVolumesSuspense<TData = {
    data: VolumeOut[];
}>(options: {
    params: ListVolumesParams;
    query?: Omit<UseSuspenseQueryOptions<{
        data: VolumeOut[];
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: listVolumesKey(options.params),
        queryFn: ()=>listVolumes(options.params),
        ...options?.query
    });
}
export const health_check_health_get = async (options?: RequestInit): Promise<{
    data: Record<string, string>;
}> =>{
    const res = await fetch("/health", {
        ...options,
        method: "GET"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export const health_check_health_getKey = ()=>{
    return [
        "/health"
    ] as const;
};
export function useHealth_check_health_get<TData = {
    data: Record<string, string>;
}>(options?: {
    query?: Omit<UseQueryOptions<{
        data: Record<string, string>;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useQuery({
        queryKey: health_check_health_getKey(),
        queryFn: ()=>health_check_health_get(),
        ...options?.query
    });
}
export function useHealth_check_health_getSuspense<TData = {
    data: Record<string, string>;
}>(options?: {
    query?: Omit<UseSuspenseQueryOptions<{
        data: Record<string, string>;
    }, ApiError, TData>, "queryKey" | "queryFn">;
}) {
    return useSuspenseQuery({
        queryKey: health_check_health_getKey(),
        queryFn: ()=>health_check_health_get(),
        ...options?.query
    });
}
export const invocations_endpoint_invocations_post = async (options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/invocations", {
        ...options,
        method: "POST"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useInvocations_endpoint_invocations_post(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, void>;
}) {
    return useMutation({
        mutationFn: ()=>invocations_endpoint_invocations_post(),
        ...options?.mutation
    });
}
export const responses_endpoint_responses_post = async (options?: RequestInit): Promise<{
    data: unknown;
}> =>{
    const res = await fetch("/responses", {
        ...options,
        method: "POST"
    });
    if (!res.ok) {
        const body = await res.text();
        let parsed: unknown;
        try {
            parsed = JSON.parse(body);
        } catch  {
            parsed = body;
        }
        throw new ApiError(res.status, res.statusText, parsed);
    }
    return {
        data: await res.json()
    };
};
export function useResponses_endpoint_responses_post(options?: {
    mutation?: UseMutationOptions<{
        data: unknown;
    }, ApiError, void>;
}) {
    return useMutation({
        mutationFn: ()=>responses_endpoint_responses_post(),
        ...options?.mutation
    });
}
